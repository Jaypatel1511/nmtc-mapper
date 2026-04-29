"""
NMTCMapper — main public API for NMTC eligibility checking.
"""
import pandas as pd
from typing import Optional

from nmtcmapper.data.loader import load_eligibility_table
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
        Initialize NMTCMapper and load the eligibility table.

        Args:
            force_reload: Re-download the eligibility file even if cached
        """
        print("Loading NMTC eligibility table...")
        self._table = load_eligibility_table(force=force_reload)
        print(f"Ready. {len(self._table):,} census tracts loaded.")

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
        tract_id = geocode_address(address)
        geocode_success = tract_id is not None

        if tract_id:
            data = check_tract(tract_id, self._table)
        else:
            data = {
                "nmtc_eligible": False,
                "distress_level": "ineligible",
                "poverty_rate": None,
                "ami_ratio": None,
                "unemployment_rate": None,
                "is_non_metro": False,
                "is_high_migration_rural": False,
                "severe_distress": False,
                "deep_distress": False,
            }

        return EligibilityResult(
            address=address,
            tract_id=tract_id,
            geocode_success=geocode_success,
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
            - nmtc_eligible (bool)
            - distress_level (str: 'deep', 'severe', 'lic', 'ineligible')
            - poverty_rate (float)
            - ami_ratio (float)
            - unemployment_rate (float)
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
        eligible = df["nmtc_eligible"].sum()
        deep = (df["distress_level"] == "deep").sum()
        severe = (df["distress_level"] == "severe").sum()
        lic = (df["distress_level"] == "lic").sum()

        result = {
            "total": total,
            "nmtc_eligible": int(eligible),
            "pct_eligible": round(eligible / total * 100, 1) if total else 0,
            "deep_distress": int(deep),
            "severe_distress": int(severe),
            "lic_only": int(lic),
            "ineligible": int(total - eligible),
        }

        print(f"\nNMTC Eligibility Summary")
        print(f"{'='*40}")
        print(f"  Total addresses:    {total:,}")
        print(f"  NMTC Eligible:      {eligible:,} ({result['pct_eligible']}%)")
        print(f"  ── Deep Distress:   {deep:,}")
        print(f"  ── Severe Distress: {severe:,}")
        print(f"  ── LIC Only:        {lic:,}")
        print(f"  Not Eligible:       {total - eligible:,}")
        print()
        return result

    @property
    def tract_count(self) -> int:
        return len(self._table)

    @property
    def eligible_tract_count(self) -> int:
        return int(self._table["nmtc_eligible"].sum())
