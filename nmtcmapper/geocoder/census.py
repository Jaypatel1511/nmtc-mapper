"""
Census Geocoding API wrapper.
Converts addresses to census tract GEOIDs using the free Census Bureau API.
"""
import requests
import pandas as pd
import io
import time
from typing import Optional

from nmtcmapper.data.schema import (
    CENSUS_GEOCODER_URL, CENSUS_GEOCODER_BATCH_URL
)


def geocode_address(address: str, retry: int = 2) -> Optional[str]:
    """
    Geocode a single address to an 11-digit census tract GEOID.

    Uses the free Census Bureau Geocoding API — no API key required.

    Args:
        address: Full address string e.g. "1234 S Michigan Ave, Chicago, IL 60605"
        retry:   Number of retries on failure

    Returns:
        11-digit census tract GEOID (state+county+tract) or None if not found
    """
    params = {
        "street":       _parse_street(address),
        "city":         _parse_city(address),
        "state":        _parse_state(address),
        "zip":          _parse_zip(address),
        "benchmark":    "Public_AR_Current",
        "vintage":      "Current_Current",
        "layers":       "Census Tracts",
        "format":       "json",
    }

    for attempt in range(retry + 1):
        try:
            response = requests.get(
                CENSUS_GEOCODER_URL, params=params, timeout=15
            )
            response.raise_for_status()
            data = response.json()

            matches = data.get("result", {}).get("addressMatches", [])
            if not matches:
                return None

            geo = matches[0].get("geographies", {})
            tracts = geo.get("Census Tracts", [])
            if not tracts:
                return None

            state  = tracts[0].get("STATE", "")
            county = tracts[0].get("COUNTY", "")
            tract  = tracts[0].get("TRACT", "")

            if state and county and tract:
                return f"{state}{county}{tract}"
            return None

        except Exception as e:
            if attempt < retry:
                time.sleep(1)
            else:
                return None


def geocode_batch(
    df: pd.DataFrame,
    address_col: str = "address",
    batch_size: int = 100,
    sleep_between: float = 1.0,
) -> pd.DataFrame:
    """
    Geocode a batch of addresses using the Census batch geocoder.

    Args:
        df:             DataFrame with address column
        address_col:    Name of the address column
        batch_size:     Addresses per batch (max 10,000 per Census API)
        sleep_between:  Seconds to sleep between batches

    Returns:
        DataFrame with added 'tract_id' column
    """
    df = df.copy()
    df["tract_id"] = None

    total = len(df)
    print(f"Geocoding {total:,} addresses in batches of {batch_size}...")

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = df.iloc[start:end]

        print(f"  Batch {start//batch_size + 1}: rows {start}–{end}")

        try:
            tract_ids = _batch_geocode_census(batch, address_col)
            df.loc[batch.index, "tract_id"] = tract_ids
        except Exception as e:
            print(f"  Batch failed: {e} — falling back to single geocoding")
            for idx, row in batch.iterrows():
                df.at[idx, "tract_id"] = geocode_address(row[address_col])

        if end < total:
            time.sleep(sleep_between)

    matched = df["tract_id"].notna().sum()
    print(f"Geocoded {matched:,}/{total:,} addresses successfully")
    return df


def _batch_geocode_census(
    df: pd.DataFrame, address_col: str
) -> list:
    """
    Use Census batch geocoding API for a chunk of addresses.
    Returns list of tract IDs in same order as input.
    """
    # Build CSV for batch API
    rows = []
    for i, (idx, row) in enumerate(df.iterrows()):
        addr = str(row[address_col])
        street = _parse_street(addr)
        city   = _parse_city(addr)
        state  = _parse_state(addr)
        zip_   = _parse_zip(addr)
        rows.append(f'{i},"{street}","{city}","{state}","{zip_}"')

    csv_content = "\n".join(rows)

    response = requests.post(
        CENSUS_GEOCODER_BATCH_URL,
        files={"addressFile": ("addresses.csv", csv_content, "text/csv")},
        data={
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "layers": "Census Tracts",
        },
        timeout=60,
    )
    response.raise_for_status()

    result_df = pd.read_csv(
        io.StringIO(response.text),
        header=None,
        names=["id", "input_address", "match", "match_type",
               "matched_address", "coords", "tiger_line_id",
               "side", "state", "county", "tract", "block"],
        dtype=str,
    )

    tract_ids = []
    for _, row in result_df.iterrows():
        if (row.get("match") == "Match" and
                pd.notna(row.get("state")) and
                pd.notna(row.get("county")) and
                pd.notna(row.get("tract"))):
            tract_ids.append(
                f"{row['state']}{row['county']}{row['tract']}"
            )
        else:
            tract_ids.append(None)

    return tract_ids


def _parse_street(address: str) -> str:
    parts = [p.strip() for p in address.split(",")]
    return parts[0] if parts else address


def _parse_city(address: str) -> str:
    parts = [p.strip() for p in address.split(",")]
    return parts[1] if len(parts) > 1 else ""


def _parse_state(address: str) -> str:
    parts = [p.strip() for p in address.split(",")]
    if len(parts) > 2:
        state_zip = parts[2].strip().split()
        return state_zip[0] if state_zip else ""
    return ""


def _parse_zip(address: str) -> str:
    parts = [p.strip() for p in address.split(",")]
    if len(parts) > 2:
        state_zip = parts[2].strip().split()
        return state_zip[1] if len(state_zip) > 1 else ""
    return ""
