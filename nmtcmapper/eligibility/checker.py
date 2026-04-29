"""
NMTC eligibility checker — applies eligibility rules to census tract data.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from nmtcmapper.data.schema import DISTRESS_LEVELS


@dataclass
class EligibilityResult:
    """Result of a single address NMTC eligibility check."""
    address: str
    tract_id: Optional[str]
    nmtc_eligible: bool
    distress_level: str
    poverty_rate: Optional[float]
    ami_ratio: Optional[float]
    unemployment_rate: Optional[float]
    is_non_metro: bool
    is_high_migration_rural: bool
    severe_distress: bool
    deep_distress: bool
    geocode_success: bool

    @property
    def distress_description(self) -> str:
        return DISTRESS_LEVELS.get(self.distress_level, "Unknown")

    def summary(self) -> None:
        print(f"\nNMTC Eligibility Result")
        print(f"{'='*50}")
        print(f"  Address:          {self.address}")
        print(f"  Census Tract:     {self.tract_id or 'Not found'}")
        print(f"  NMTC Eligible:    {'✅ YES' if self.nmtc_eligible else '❌ NO'}")
        print(f"  Distress Level:   {self.distress_level.upper()}")
        print(f"  Description:      {self.distress_description}")
        if self.poverty_rate is not None:
            print(f"\n  Poverty Rate:     {self.poverty_rate*100:.1f}%")
        if self.ami_ratio is not None:
            print(f"  AMI Ratio:        {self.ami_ratio*100:.1f}%")
        if self.unemployment_rate is not None:
            print(f"  Unemployment:     {self.unemployment_rate*100:.1f}%")
        print(f"  Non-Metro:        {'Yes' if self.is_non_metro else 'No'}")
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
        return {
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

    row = eligibility_table.loc[tract_id]
    return {
        "nmtc_eligible":         bool(row.get("nmtc_eligible", False)),
        "distress_level":        str(row.get("distress_level", "ineligible")),
        "poverty_rate":          row.get("poverty_rate"),
        "ami_ratio":             row.get("ami_ratio"),
        "unemployment_rate":     row.get("unemployment_rate"),
        "is_non_metro":          bool(row.get("is_non_metro", False)),
        "is_high_migration_rural": bool(row.get("is_high_migration_rural", False)),
        "severe_distress":       bool(row.get("severe_distress", False)),
        "deep_distress":         bool(row.get("deep_distress", False)),
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
        "is_high_migration_rural", "severe_distress", "deep_distress",
    ]

    for col in eligibility_cols:
        df[col] = None

    for idx, row in df.iterrows():
        tract_id = row.get(tract_col)
        if pd.notna(tract_id) and tract_id in eligibility_table.index:
            result = check_tract(str(tract_id), eligibility_table)
            for col, val in result.items():
                df.at[idx, col] = val
        else:
            df.at[idx, "nmtc_eligible"] = False
            df.at[idx, "distress_level"] = "ineligible"

    return df
