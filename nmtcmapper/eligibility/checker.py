"""
NMTC eligibility checker — applies eligibility rules to census tract data.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from nmtcmapper.data.schema import DISTRESS_LEVELS


@dataclass
class EligibilityResult:
    """Result of a single address NMTC eligibility check.

    ``nmtc_eligible`` is TRI-STATE (0.4.0): True (verified eligible), False
    (verified ineligible — the table explicitly says NO), or None
    (INDETERMINATE — geocode no-match, or the tract is absent from the ~85k
    universe). None must never be read as a falsy "ineligible": see
    ``eligibility_status`` and ``summary()``.
    """
    address: str
    tract_id: Optional[str]
    nmtc_eligible: Optional[bool]
    distress_level: str
    poverty_rate: Optional[float]
    ami_ratio: Optional[float]
    unemployment_rate: Optional[float]
    is_non_metro: bool
    is_high_migration_rural: bool
    is_nmtc_native_area: bool
    severe_distress: bool
    deep_distress: bool
    geocode_success: bool
    is_opportunity_zone: bool = False
    tract_found: bool = True

    @property
    def distress_description(self) -> str:
        return DISTRESS_LEVELS.get(self.distress_level, "Unknown")

    @property
    def eligibility_status(self) -> str:
        """Four-way status distinguishing the indeterminate cases from verdicts.

        verified-eligible / verified-ineligible / not-found / geocode-failed.
        """
        if not self.geocode_success:
            return "geocode-failed"
        if not self.tract_found:
            return "not-found"
        # tract_found is True here, so nmtc_eligible is a real bool (never None).
        return "verified-eligible" if self.nmtc_eligible else "verified-ineligible"

    def summary(self) -> None:
        print(f"\nNMTC Eligibility Result")
        print(f"{'='*50}")
        print(f"  Address:          {self.address}")
        print(f"  Census Tract:     {self.tract_id or 'Not found'}")
        # Tri-state: an indeterminate result must NOT print "❌ NO". The reason it
        # is unknown is qualified inline on the same line (not in a footer).
        if self.nmtc_eligible is None:
            if not self.geocode_success:
                elig = "❓ UNKNOWN — address could not be geocoded (indeterminate, NOT ineligible)"
            else:
                elig = "❓ UNKNOWN — tract not in eligibility table (indeterminate, NOT ineligible)"
        elif self.nmtc_eligible:
            elig = "✅ YES"
        else:
            elig = "❌ NO"
        print(f"  NMTC Eligible:    {elig}")
        print(f"  Distress Level:   {self.distress_level.upper()}")
        print(f"  Description:      {self.distress_description}")
        if self.poverty_rate is not None:
            print(f"\n  Poverty Rate:     {self.poverty_rate*100:.1f}%")
        if self.ami_ratio is not None:
            print(f"  AMI Ratio:        {self.ami_ratio*100:.1f}%")
        if self.unemployment_rate is not None:
            print(f"  Unemployment:     {self.unemployment_rate*100:.1f}%")
        print(f"  Non-Metro:        {'Yes' if self.is_non_metro else 'No'}")
        print(f"  Opportunity Zone: {'Yes' if self.is_opportunity_zone else 'No'}")
        print(f"  High Migration:   {'Yes' if self.is_high_migration_rural else 'No'}")
        print()


def check_tract(
    tract_id: str,
    eligibility_table: pd.DataFrame,
) -> dict:
    """
    Check NMTC eligibility for a known census tract ID.

    Args:
        tract_id:          11-digit census tract GEOID
        eligibility_table: DataFrame indexed by tract_id

    Returns:
        Dict with eligibility fields
    """
    if tract_id not in eligibility_table.index:
        # LOOKUP MISS (Fix 3). The table is the full ~85k-tract universe with an
        # explicit YES/NO flag, so a tract that is ABSENT is not "ineligible" —
        # it is a bad/unknown tract id or a vintage mismatch. Return an
        # INDETERMINATE verdict (nmtc_eligible None, distress "unknown", metrics
        # None) and an explicit tract_found=False so a caller can tell "table
        # says NO" from "tract absent" without having to notice metrics are None.
        return {
            "nmtc_eligible": None,
            "distress_level": "unknown",
            "poverty_rate": None,
            "ami_ratio": None,
            "unemployment_rate": None,
            "is_non_metro": False,
            "is_high_migration_rural": False,
            "is_nmtc_native_area": False,
            "severe_distress": False,
            "deep_distress": False,
            "tract_found": False,
        }

    row = eligibility_table.loc[tract_id]
    return {
        "nmtc_eligible":         bool(row.get("nmtc_eligible", False)),
        "distress_level":        str(row.get("distress_level", "ineligible")),
        "poverty_rate":          row.get("poverty_rate"),
        "ami_ratio":             row.get("ami_ratio"),
        "unemployment_rate":     row.get("unemployment_rate"),
        "is_non_metro":          bool(row.get("is_non_metro", False)),
        "is_high_migration_rural": bool(row.get("is_high_migration_rural", False)),
        "is_nmtc_native_area":   bool(row.get("is_nmtc_native_area", False)),
        "severe_distress":       bool(row.get("severe_distress", False)),
        "deep_distress":         bool(row.get("deep_distress", False)),
        "tract_found":           True,
    }


def enrich_dataframe(
    df: pd.DataFrame,
    eligibility_table: pd.DataFrame,
    tract_col: str = "tract_id",
) -> pd.DataFrame:
    """
    Add NMTC eligibility columns to a DataFrame that already has tract IDs.

    Args:
        df:                DataFrame with tract_id column
        eligibility_table: Full eligibility lookup table
        tract_col:         Name of the tract ID column

    Returns:
        DataFrame with added eligibility columns
    """
    df = df.copy()

    eligibility_cols = [
        "nmtc_eligible", "distress_level", "poverty_rate",
        "ami_ratio", "unemployment_rate", "is_non_metro",
        "is_high_migration_rural", "is_nmtc_native_area", "severe_distress", "deep_distress",
    ]

    for col in eligibility_cols:
        df[col] = None
    # Additive column (0.4.0) distinguishing the four outcomes:
    # verified-eligible / verified-ineligible / not-found / geocode-failed.
    df["eligibility_status"] = None

    for idx, row in df.iterrows():
        tract_id = row.get(tract_col)
        if pd.isna(tract_id):
            # No tract resolved (geocoding failed / no tract supplied) —
            # INDETERMINATE, never a fabricated False/"ineligible".
            df.at[idx, "nmtc_eligible"] = None
            df.at[idx, "distress_level"] = "unknown"
            df.at[idx, "eligibility_status"] = "geocode-failed"
            continue

        result = check_tract(str(tract_id), eligibility_table)
        found = result.pop("tract_found")
        for col, val in result.items():
            df.at[idx, col] = val
        if not found:
            df.at[idx, "eligibility_status"] = "not-found"
        elif result["nmtc_eligible"]:
            df.at[idx, "eligibility_status"] = "verified-eligible"
        else:
            df.at[idx, "eligibility_status"] = "verified-ineligible"

    return df
