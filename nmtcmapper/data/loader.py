"""
Download and cache the CDFI Fund NMTC eligibility file.
Builds a lookup table of all eligible census tracts.
"""
import os
import requests
import pandas as pd
from pathlib import Path

from nmtcmapper.data.schema import (
    CACHE_DIR, CDFI_FUND_LIC_URL_2020,
    ELIGIBILITY_FILE_COLUMNS,
    LIC_POVERTY_RATE_THRESHOLD,
    LIC_AMI_RATIO_METRO_THRESHOLD,
    LIC_AMI_RATIO_RURAL_THRESHOLD,
    SEVERE_POVERTY_THRESHOLD, SEVERE_AMI_THRESHOLD,
    SEVERE_UNEMPLOYMENT_MULTIPLIER, NATIONAL_UNEMPLOYMENT_RATE,
    DEEP_POVERTY_THRESHOLD, DEEP_AMI_THRESHOLD,
    DEEP_UNEMPLOYMENT_MULTIPLIER,
)


def get_cache_dir() -> Path:
    path = Path(CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(filename: str) -> Path:
    return get_cache_dir() / filename


def download_eligibility_file(force: bool = False) -> Path:
    filename = "NMTC_LIC_Eligibility_2016_2020.xlsx"
    path = _cache_path(filename)
    if path.exists() and not force:
        print(f"Using cached eligibility file: {path}")
        return path
    print("Downloading NMTC eligibility file from CDFI Fund...")
    try:
        response = requests.get(CDFI_FUND_LIC_URL_2020, stream=True, timeout=120)
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Saved to {path}")
        return path
    except Exception as e:
        print(f"Download failed: {e}")
        return None


def load_eligibility_table(force: bool = False) -> pd.DataFrame:
    path = download_eligibility_file(force=force)
    if path is None or not path.exists():
        print("Using built-in sample eligibility data.")
        return _build_sample_table()
    print(f"Loading eligibility table from {path}...")
    try:
        df = pd.read_excel(path, dtype=str)
        return _process_eligibility_table(df)
    except Exception as e:
        print(f"Error loading file: {e}. Using sample data.")
        return _build_sample_table()


def _process_eligibility_table(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip().str.upper()
    col_map = {k: v for k, v in ELIGIBILITY_FILE_COLUMNS.items() if k in df.columns}
    df = df.rename(columns=col_map)
    if "tract_id" not in df.columns:
        if all(c in df.columns for c in ["state", "county", "tract"]):
            df["tract_id"] = (
                df["state"].str.zfill(2) +
                df["county"].str.zfill(3) +
                df["tract"].str.zfill(6)
            )
    for col in ["poverty_rate", "ami_ratio", "unemployment_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["is_non_metro", "is_high_migration_rural"]:
        if col in df.columns:
            df[col] = df[col].isin({"Y", "YES", "1", "True", "TRUE", "X"})
    df = _compute_eligibility(df)
    if "tract_id" in df.columns:
        df = df.set_index("tract_id")
    print(f"Eligibility table loaded: {len(df):,} census tracts")
    return df


def _compute_eligibility(df: pd.DataFrame) -> pd.DataFrame:
    pr = df.get("poverty_rate", pd.Series(dtype=float))
    ami = df.get("ami_ratio", pd.Series(dtype=float))
    unemp = df.get("unemployment_rate", pd.Series(dtype=float))
    non_metro = df.get("is_non_metro", pd.Series(False, index=df.index))
    if "is_nmtc_native_area" not in df.columns:
        df["is_nmtc_native_area"] = False

    poverty_lic = pr >= LIC_POVERTY_RATE_THRESHOLD
    ami_lic = (
        (non_metro & (ami <= LIC_AMI_RATIO_RURAL_THRESHOLD)) |
        (~non_metro & (ami <= LIC_AMI_RATIO_METRO_THRESHOLD))
    )
    df["nmtc_eligible"] = poverty_lic | ami_lic

    sev_poverty = pr >= SEVERE_POVERTY_THRESHOLD
    sev_ami = ami <= SEVERE_AMI_THRESHOLD
    sev_unemp = unemp >= (NATIONAL_UNEMPLOYMENT_RATE * SEVERE_UNEMPLOYMENT_MULTIPLIER)
    df["severe_distress"] = sev_poverty | sev_ami | sev_unemp

    deep_poverty = pr >= DEEP_POVERTY_THRESHOLD
    deep_ami = ami <= DEEP_AMI_THRESHOLD
    deep_unemp = unemp >= (NATIONAL_UNEMPLOYMENT_RATE * DEEP_UNEMPLOYMENT_MULTIPLIER)
    df["deep_distress"] = deep_poverty | deep_ami | deep_unemp

    def distress_label(row):
        if row.get("deep_distress"):
            return "deep"
        elif row.get("severe_distress"):
            return "severe"
        elif row.get("nmtc_eligible"):
            return "lic"
        return "ineligible"

    df["distress_level"] = df.apply(distress_label, axis=1)
    return df


def _build_sample_table() -> pd.DataFrame:
    sample_tracts = [
        ("17031840100", 0.38, 0.55, 0.12, False, False, False),
        ("17031839100", 0.42, 0.48, 0.15, False, False, False),
        ("17031010100", 0.18, 0.92, 0.04, False, False, False),
        ("36061015900", 0.35, 0.60, 0.11, False, False, False),
        ("36061019100", 0.28, 0.72, 0.09, False, False, False),
        ("36047052200", 0.14, 0.88, 0.05, False, False, False),
        ("26163518300", 0.45, 0.45, 0.18, False, False, False),
        ("26163520100", 0.32, 0.62, 0.13, False, False, False),
        ("13121010400", 0.29, 0.68, 0.10, False, False, False),
        ("48113010900", 0.22, 0.78, 0.07, False, False, False),
        ("17019000100", 0.15, 0.95, 0.03, True,  True,  False),
        ("26001010100", 0.18, 0.88, 0.06, True,  False, False),
    ]
    rows = []
    for tid, pr, ami, unemp, non_metro, high_migration, native_area in sample_tracts:
        rows.append({
            "tract_id": tid,
            "state": tid[:2],
            "poverty_rate": pr,
            "ami_ratio": ami,
            "unemployment_rate": unemp,
            "is_non_metro": non_metro,
            "is_high_migration_rural": high_migration,
            "is_nmtc_native_area": native_area,
        })
    df = pd.DataFrame(rows)
    df = _compute_eligibility(df)
    df = df.set_index("tract_id")
    return df


# ── Opportunity Zone lookup ───────────────────────────────────────────────────

def load_opportunity_zones(force: bool = False) -> set:
    """
    Load the set of Opportunity Zone census tract IDs.
    Returns a set of 11-digit FIPS codes designated as QOZs.

    Uses IRS Notice 2018-48 list (8,764 tracts).
    Falls back to a known sample set if download fails.
    """
    filename = "QOZ_Tracts_2018.xlsx"
    path = _cache_path(filename)

    if not path.exists() or force:
        try:
            from nmtcmapper.data.schema import OZ_URL_2018
            print("Downloading Opportunity Zone tract list...")
            response = requests.get(OZ_URL_2018, stream=True, timeout=60)
            response.raise_for_status()
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Saved to {path}")
        except Exception as e:
            print(f"OZ download failed: {e}. Using sample OZ data.")
            return _sample_oz_tracts()

    try:
        df = pd.read_excel(path, dtype=str)
        df.columns = df.columns.str.strip().str.upper()
        # Try common column names
        for col in ["GEOID", "CENSUS_TRACT", "TRACT_ID", "TRACT"]:
            if col in df.columns:
                tracts = set(df[col].str.strip().str.zfill(11).tolist())
                print(f"Loaded {len(tracts):,} Opportunity Zone tracts")
                return tracts
    except Exception as e:
        print(f"OZ file parse error: {e}. Using sample data.")

    return _sample_oz_tracts()


def _sample_oz_tracts() -> set:
    """Known OZ tracts for testing — subset of real designations."""
    return {
        "17031840100",  # Chicago South Side
        "17031839100",  # Chicago West Side
        "26163518300",  # Detroit
        "36061015900",  # NYC Bronx
        "13121010400",  # Atlanta
        "48113010900",  # Dallas
    }
