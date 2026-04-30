"""
Census Geocoding API wrapper with async batch processing.
Converts addresses to 11-digit census tract FIPS codes.
Uses asyncio + aiohttp for high-throughput batch geocoding.
"""
import asyncio
import aiohttp
import requests
import pandas as pd
import io
import time
from typing import Optional
from tqdm import tqdm

from nmtcmapper.data.schema import (
    CENSUS_GEOCODER_URL,
    CENSUS_GEOCODER_BATCH_URL,
)

# Rate limiting
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT         = 15
MAX_RETRIES             = 3
RETRY_BACKOFF           = 2.0   # seconds


async def _geocode_single_async(
    session: aiohttp.ClientSession,
    address: str,
    semaphore: asyncio.Semaphore,
    retries: int = MAX_RETRIES,
) -> Optional[str]:
    """
    Async geocode a single address to an 11-digit census tract FIPS code.

    Args:
        session:   aiohttp ClientSession
        address:   Full address string
        semaphore: Semaphore to limit concurrent requests
        retries:   Number of retries on failure

    Returns:
        11-digit FIPS code or None
    """
    params = {
        "street":    _parse_street(address),
        "city":      _parse_city(address),
        "state":     _parse_state(address),
        "zip":       _parse_zip(address),
        "benchmark": "Public_AR_Current",
        "vintage":   "Current_Current",
        "layers":    "Census Tracts",
        "format":    "json",
    }

    async with semaphore:
        for attempt in range(retries + 1):
            try:
                async with session.get(
                    CENSUS_GEOCODER_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    matches = data.get("result", {}).get("addressMatches", [])
                    if not matches:
                        return None

                    geo    = matches[0].get("geographies", {})
                    tracts = geo.get("Census Tracts", [])
                    if not tracts:
                        return None

                    state  = tracts[0].get("STATE", "")
                    county = tracts[0].get("COUNTY", "")
                    tract  = tracts[0].get("TRACT", "")

                    if state and county and tract:
                        return f"{state}{county}{tract}"
                    return None

            except Exception:
                if attempt < retries:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                else:
                    return None


async def _batch_geocode_async(addresses: list) -> list:
    """
    Async batch geocode a list of addresses.

    Args:
        addresses: List of address strings

    Returns:
        List of FIPS codes (None for failed lookups) in same order
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    results   = [None] * len(addresses)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _geocode_single_async(session, addr, semaphore)
            for addr in addresses
        ]

        with tqdm(total=len(tasks), desc="Geocoding", unit="addr") as pbar:
            for i, coro in enumerate(asyncio.as_completed(
                {asyncio.create_task(t): i for i, t in enumerate(tasks)}
            )):
                pass

        # Run all tasks and preserve order
        results = await asyncio.gather(*tasks)

    return list(results)


def geocode_address(address: str) -> Optional[str]:
    """
    Geocode a single address synchronously.
    Uses the Census Bureau Geocoding API — no API key required.

    Args:
        address: Full address e.g. "1234 S Michigan Ave, Chicago, IL 60605"

    Returns:
        11-digit census tract FIPS code or None
    """
    params = {
        "street":    _parse_street(address),
        "city":      _parse_city(address),
        "state":     _parse_state(address),
        "zip":       _parse_zip(address),
        "benchmark": "Public_AR_Current",
        "vintage":   "Current_Current",
        "layers":    "Census Tracts",
        "format":    "json",
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                CENSUS_GEOCODER_URL, params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            matches = data.get("result", {}).get("addressMatches", [])
            if not matches:
                return None

            geo    = matches[0].get("geographies", {})
            tracts = geo.get("Census Tracts", [])
            if not tracts:
                return None

            state  = tracts[0].get("STATE", "")
            county = tracts[0].get("COUNTY", "")
            tract  = tracts[0].get("TRACT", "")

            if state and county and tract:
                return f"{state}{county}{tract}"
            return None

        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
            else:
                return None


def geocode_batch(
    df: pd.DataFrame,
    address_col: str = "address",
    batch_size: int = 500,
    use_async: bool = True,
) -> pd.DataFrame:
    """
    Geocode a batch of addresses using async processing.

    Args:
        df:          DataFrame with address column
        address_col: Name of the address column
        batch_size:  Addresses per chunk
        use_async:   Use async geocoding (recommended for >100 addresses)

    Returns:
        DataFrame with added 'tract_id' column
    """
    df = df.copy()
    addresses = df[address_col].tolist()
    total = len(addresses)

    print(f"Geocoding {total:,} addresses "
          f"({'async' if use_async else 'sync'})...")

    if use_async and total > 1:
        # Process in chunks to avoid memory issues
        all_results = []
        for start in range(0, total, batch_size):
            chunk = addresses[start:start + batch_size]
            print(f"  Chunk {start//batch_size + 1}: "
                  f"rows {start}–{min(start+batch_size, total)}")
            try:
                results = asyncio.run(_batch_geocode_async(chunk))
            except RuntimeError:
                # Already in event loop (e.g. Jupyter)
                import nest_asyncio
                nest_asyncio.apply()
                results = asyncio.run(_batch_geocode_async(chunk))
            all_results.extend(results)
        df["tract_id"] = all_results
    else:
        tract_ids = []
        for addr in tqdm(addresses, desc="Geocoding", unit="addr"):
            tract_ids.append(geocode_address(addr))
        df["tract_id"] = tract_ids

    matched = df["tract_id"].notna().sum()
    print(f"Geocoded {matched:,}/{total:,} addresses "
          f"({matched/total*100:.1f}% match rate)")
    return df


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
