"""
NMTCMapper — main public API for NMTC eligibility checking.
"""
import pandas as pd
from typing import Optional

from nmtcmapper.data.loader import (
    load_eligibility_table, load_opportunity_zones,
    load_sample_table, _sample_oz_tracts,
)
from nmtcmapper.geocoder.census import geocode_address, geocode_batch
from nmtcmapper.eligibility.checker import (
    check_tract, enrich_dataframe, EligibilityResult
)


class NMTCMapper:
    """
    Check NMTC eligibility for addresses or census tracts.

    Usage:
        mapper = NMTCMapper()

        # Single address
        result = mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")
        result.summary()

        # Known census tract
        result = mapper.check_tract("17031840100")

        # Batch — DataFrame of addresses
        df = pd.read_csv("projects.csv")
        df = mapper.enrich(df, address_col="address")
    """

    def __init__(self, force_reload: bool = False):
        """
        Initialize NMTCMapper against the real CDFI Fund data.

        Raises on any download or parse failure (EligibilityDownloadError /
        EligibilityParseError / OZDownloadError / OZParseError) rather than
        silently substituting demo data. For offline demos/tests, use the
        explicit ``NMTCMapper.from_sample()`` constructor instead.

        Args:
            force_reload: Re-download the eligibility file even if cached
        """
        print("Loading NMTC eligibility table...")
        self._table = load_eligibility_table(force=force_reload)
        print(f"Ready. {len(self._table):,} census tracts loaded.")
        self._oz_tracts = load_opportunity_zones()
        print(f"Opportunity Zones loaded: {len(self._oz_tracts):,} tracts")
        self.data_source = "cdfi_fund"

    @classmethod
    def from_sample(cls) -> "NMTCMapper":
        """
        Construct a mapper on the built-in synthetic sample data — no network.

        WARNING: the sample is 12 synthetic-vintage tracts (+ 6 OZ tracts) for
        demos, examples, and tests. It is NEVER valid for a real NMTC eligibility
        answer. The resulting mapper is stamped ``data_source == "sample"`` so
        downstream code can assert provenance. Use ``NMTCMapper()`` for real data.
        """
        obj = cls.__new__(cls)
        obj._table = load_sample_table()
        obj._oz_tracts = _sample_oz_tracts()
        obj.data_source = "sample"
        return obj

    def __repr__(self) -> str:
        return (
            f"NMTCMapper(data_source={self.data_source!r}, "
            f"tracts={len(self._table):,}, oz_tracts={len(self._oz_tracts):,})"
        )

    def check_address(self, address: str) -> EligibilityResult:
        """
        Check NMTC eligibility for a single address.

        Geocodes the address to a census tract using the free
        Census Bureau API, then looks up eligibility.

        Args:
            address: Full address string e.g.
                     "1234 S Michigan Ave, Chicago, IL 60605"

        Returns:
            EligibilityResult with eligibility flags and tract data
        """
        # geocode_address raises typed geocoder errors (GeocoderTransportError /
        # AmbiguousAddressError) — DO NOT catch them here; let them propagate so
        # a caller can tell a real failure from a real answer (Fix 2). A genuine
        # no-match returns None.
        tract_id = geocode_address(address)

        if tract_id is None:
            # Genuine no-match -> INDETERMINATE, never False/"ineligible".
            return EligibilityResult(
                address=address,
                tract_id=None,
                geocode_success=False,
                tract_found=False,
                nmtc_eligible=None,
                distress_level="unknown",
                poverty_rate=None,
                ami_ratio=None,
                unemployment_rate=None,
                is_non_metro=False,
                is_high_migration_rural=False,
                is_nmtc_native_area=False,
                severe_distress=False,
                deep_distress=False,
                is_opportunity_zone=False,
            )

        data = check_tract(tract_id, self._table)
        data["is_opportunity_zone"] = tract_id in self._oz_tracts
        return EligibilityResult(
            address=address,
            tract_id=tract_id,
            geocode_success=True,
            **data,
        )

    def check_tract(self, tract_id: str) -> EligibilityResult:
        """
        Check NMTC eligibility for a known 11-digit census tract GEOID.

        Args:
            tract_id: 11-digit GEOID e.g. "17031840100"

        Returns:
            EligibilityResult with eligibility flags
        """
        data = check_tract(tract_id, self._table)
        data["is_opportunity_zone"] = tract_id in self._oz_tracts
        return EligibilityResult(
            address=f"Census Tract {tract_id}",
            tract_id=tract_id,
            geocode_success=True,
            **data,
        )

    def enrich(
        self,
        df: pd.DataFrame,
        address_col: str = "address",
        tract_col: str = None,
        batch_size: int = 100,
    ) -> pd.DataFrame:
        """
        Add NMTC eligibility columns to a DataFrame.

        If tract_col is provided, uses existing tract IDs (no geocoding).
        If address_col is provided, geocodes addresses first.

        Args:
            df:          DataFrame with address or tract ID column
            address_col: Column with full address strings
            tract_col:   Column with 11-digit tract GEOIDs (skips geocoding)
            batch_size:  Addresses per geocoding batch

        Returns:
            DataFrame with added columns:
            - nmtc_eligible (Optional[bool]: True / False / None — None is
              INDETERMINATE, never a falsy "ineligible")
            - eligibility_status (str: 'verified-eligible', 'verified-ineligible',
              'not-found', 'geocode-failed')
            - distress_level (str: 'deep', 'severe', 'lic', 'ineligible', 'unknown')
            - poverty_rate (Optional[float])
            - ami_ratio (Optional[float])
            - unemployment_rate (Optional[float])
            - is_non_metro (bool)
            - severe_distress (bool)
            - deep_distress (bool)
        """
        df = df.copy()

        if tract_col and tract_col in df.columns:
            print(f"Using existing tract IDs from column '{tract_col}'")
            return enrich_dataframe(df, self._table, tract_col=tract_col)

        print(f"Geocoding addresses from column '{address_col}'...")
        df = geocode_batch(df, address_col=address_col, batch_size=batch_size)
        return enrich_dataframe(df, self._table, tract_col="tract_id")

    def eligible_count(self, df: pd.DataFrame) -> dict:
        """
        Summarize NMTC eligibility across a DataFrame.
        Requires df to have 'nmtc_eligible' and 'distress_level' columns.
        """
        if "nmtc_eligible" not in df.columns:
            raise ValueError("Run .enrich() first to add eligibility columns.")

        total = len(df)
        # Tri-state sweep: nmtc_eligible is Optional[bool] and the column can
        # hold None. Count each state EXPLICITLY — never `total - eligible`,
        # which would fold every indeterminate (None) row into "ineligible" and
        # fabricate a verified-ineligible tally.
        col = df["nmtc_eligible"]
        eligible = int((col == True).sum())
        ineligible = int((col == False).sum())
        indeterminate = int(total - eligible - ineligible)  # None / not-found / geocode-failed
        deep = int((df["distress_level"] == "deep").sum())
        severe = int((df["distress_level"] == "severe").sum())
        lic = int((df["distress_level"] == "lic").sum())

        result = {
            "total": total,
            "nmtc_eligible": eligible,
            "pct_eligible": round(eligible / total * 100, 1) if total else 0,
            "deep_distress": deep,
            "severe_distress": severe,
            "lic_only": lic,
            "ineligible": ineligible,
            "indeterminate": indeterminate,
        }

        print(f"\nNMTC Eligibility Summary")
        print(f"{'='*40}")
        print(f"  Total addresses:    {total:,}")
        print(f"  NMTC Eligible:      {eligible:,} ({result['pct_eligible']}%)")
        print(f"  ── Deep Distress:   {deep:,}")
        print(f"  ── Severe Distress: {severe:,}")
        print(f"  ── LIC Only:        {lic:,}")
        print(f"  Not Eligible:       {ineligible:,}")
        print(f"  Indeterminate:      {indeterminate:,} (no match / tract absent — NOT ineligible)")
        print()
        return result

    @property
    def tract_count(self) -> int:
        return len(self._table)

    @property
    def oz_tract_count(self) -> int:
        return len(self._oz_tracts)

    @property
    def eligible_tract_count(self) -> int:
        return int(self._table["nmtc_eligible"].sum())
