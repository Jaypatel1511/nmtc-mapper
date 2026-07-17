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
from nmtcmapper.exceptions import (
    GeocoderTransportError, AmbiguousAddressError,
)

# Rate limiting
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT         = 15
MAX_RETRIES             = 3
RETRY_BACKOFF           = 2.0   # seconds


def _geocoder_params(address: str) -> dict:
    return {
        "street":    _parse_street(address),
        "city":      _parse_city(address),
        "state":     _parse_state(address),
        "zip":       _parse_zip(address),
        "benchmark": "Public_AR_Current",
        "vintage":   "Current_Current",
        "layers":    "Census Tracts",
        "format":    "json",
    }


def _extract_tract_from_data(data: dict, address: str) -> Optional[str]:
    """Interpret a decoded HTTP-200 geocoder response body (0.4.0 contract).

    - zero address matches            -> None  (genuine no-match; this is the
                                         ONLY thing None means now)
    - one or more matches, all of
      which resolve to the SAME tract -> that 11-digit FIPS tract
    - matches resolving to DIFFERENT
      tracts                          -> raise AmbiguousAddressError (never
                                         silently take matches[0])

    A 200 whose matches carry no resolvable Census-Tract geography also yields
    None — there is no tract to return and it is not a transport failure.
    """
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        return None

    tracts = []
    for m in matches:
        geo = m.get("geographies", {})
        tract_recs = geo.get("Census Tracts", [])
        if not tract_recs:
            continue
        state  = tract_recs[0].get("STATE", "")
        county = tract_recs[0].get("COUNTY", "")
        tract  = tract_recs[0].get("TRACT", "")
        if state and county and tract:
            tracts.append(f"{state}{county}{tract}")

    distinct = sorted(set(tracts))
    if not distinct:
        return None
    if len(distinct) == 1:
        return distinct[0]
    raise AmbiguousAddressError(
        f"Address {address!r} geocoded to {len(matches)} matches resolving to "
        f"different census tracts {distinct}; refusing to guess which is correct."
    )


def _transport_message(kind: str, detail: str, address: str) -> str:
    return (
        f"Census geocoder request failed ({kind}) for address {address!r} "
        f"after {MAX_RETRIES + 1} attempts: {detail}"
    )


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
        11-digit FIPS code, or None for a genuine no-match (HTTP 200, zero
        matches). Raises GeocoderTransportError on transport/HTTP/decode failure
        after retries, and AmbiguousAddressError on conflicting matches — the
        same three-way contract as the sync ``geocode_address``.
    """
    params = _geocoder_params(address)

    async with semaphore:
        last_kind = last_detail = None
        for attempt in range(retries + 1):
            try:
                async with session.get(
                    CENSUS_GEOCODER_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
            except aiohttp.ClientResponseError as e:
                status = e.status
                if status == 403:
                    last_kind, last_detail = "HTTP 403 Forbidden", "access blocked"
                elif status and status >= 500:
                    last_kind, last_detail = f"HTTP {status} server error", str(e)
                else:
                    last_kind, last_detail = f"HTTP {status}", str(e)
            except asyncio.TimeoutError as e:
                last_kind, last_detail = "timeout", f"request timed out after {REQUEST_TIMEOUT}s"
            except aiohttp.ClientError as e:
                last_kind, last_detail = "connection/DNS", f"{type(e).__name__}: {e}"
            except ValueError as e:
                # aiohttp/json: non-JSON or truncated body (e.g. an HTML error page)
                last_kind, last_detail = "invalid JSON response", f"{type(e).__name__}: {e}"
            else:
                # Clean HTTP 200 with a decoded body: interpret it. AmbiguousAddressError
                # from here must propagate — it is not a transport failure to retry.
                return _extract_tract_from_data(data, address)

            if attempt < retries:
                await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))

        raise GeocoderTransportError(
            _transport_message(last_kind, last_detail, address)
        )


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
        11-digit census tract FIPS code, or None for a genuine no-match
        (HTTP 200, zero address matches). None means EXACTLY that and nothing
        else. Raises:
          - GeocoderTransportError on transport/HTTP-status/decode failure after
            retries are exhausted (403 / 5xx / timeout / connection / bad-JSON,
            each with a distinguishable message naming the address);
          - AmbiguousAddressError when the address matches multiple DIFFERENT
            census tracts.
    """
    params = _geocoder_params(address)

    last_kind = last_detail = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                CENSUS_GEOCODER_URL, params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                last_kind, last_detail = "HTTP 403 Forbidden", "access blocked"
            elif status and status >= 500:
                last_kind, last_detail = f"HTTP {status} server error", str(e)
            else:
                last_kind, last_detail = f"HTTP {status}", str(e)
        except requests.exceptions.Timeout as e:
            last_kind, last_detail = "timeout", f"request timed out after {REQUEST_TIMEOUT}s"
        except requests.exceptions.RequestException as e:
            last_kind, last_detail = "connection/DNS", f"{type(e).__name__}: {e}"
        except ValueError as e:
            # response.json() on a non-JSON / truncated body (HTML error page etc.)
            last_kind, last_detail = "invalid JSON response", f"{type(e).__name__}: {e}"
        else:
            # Clean HTTP 200 with a decoded body: interpret it. AmbiguousAddressError
            # from here must propagate — it is not a transport failure to retry.
            return _extract_tract_from_data(data, address)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * (attempt + 1))

    raise GeocoderTransportError(
        _transport_message(last_kind, last_detail, address)
    )


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
