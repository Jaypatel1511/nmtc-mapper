"""
Download and cache the CDFI Fund NMTC eligibility file.
Builds a lookup table of the FULL census-tract universe (85,395 tracts: 35,167
eligible + 50,228 ineligible), each carrying an explicit YES/NO LIC flag. A
tract ABSENT from this table is therefore unknown/indeterminate, not ineligible.
"""
import os
import re
import requests
import pandas as pd
from pathlib import Path

from nmtcmapper.exceptions import (
    EligibilityDataError, EligibilityDownloadError, EligibilityParseError,
    EligibilitySchemaError, EligibilityValueError,
    OZDataError, OZDownloadError, OZParseError,
)
from nmtcmapper.data.schema import (
    CACHE_DIR, CDFI_FUND_LIC_URL_2020,
    ELIGIBILITY_FILE_COLUMNS,
    ELIGIBILITY_XLSB_SHEET, ELIGIBILITY_XLSB_COLUMN_COUNT,
    ELIGIBILITY_XLSB_EXPECTED_HEADERS, ELIGIBILITY_MIN_ROWS,
    ELIGIBILITY_VALUE_BOUNDS,
    LIC_POVERTY_RATE_THRESHOLD,
    LIC_AMI_RATIO_METRO_THRESHOLD,
    LIC_AMI_RATIO_RURAL_THRESHOLD,
    SEVERE_POVERTY_THRESHOLD, SEVERE_AMI_THRESHOLD,
    SEVERE_UNEMPLOYMENT_MULTIPLIER, NATIONAL_UNEMPLOYMENT_RATE,
    DEEP_POVERTY_THRESHOLD, DEEP_AMI_THRESHOLD,
    DEEP_UNEMPLOYMENT_MULTIPLIER,
)


def _normalize_header(value) -> str:
    """Collapse internal whitespace, strip, and casefold a header cell."""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _validate_xlsb_header(header_vals: list) -> None:
    """Fail loud (EligibilitySchemaError) BEFORE any row is parsed if the live
    .xlsb structure does not match the expected CDFI Fund layout.

    The loader binds columns positionally, so a wrong column count or a
    renamed/re-ordered column at a bound index must be caught here — otherwise a
    poverty rate could be read out of the MFI slot and every verdict would be
    silently wrong."""
    n = len(header_vals)
    if n != ELIGIBILITY_XLSB_COLUMN_COUNT:
        raise EligibilitySchemaError(
            f"eligibility .xlsb header has {n} columns, expected "
            f"{ELIGIBILITY_XLSB_COLUMN_COUNT}. The column layout has changed — "
            f"the positional bind can no longer be trusted."
        )
    for idx, expected in ELIGIBILITY_XLSB_EXPECTED_HEADERS.items():
        actual = header_vals[idx] if idx < n else None
        if _normalize_header(actual) != _normalize_header(expected):
            raise EligibilitySchemaError(
                f"eligibility .xlsb header mismatch at column index {idx}: "
                f"expected {expected!r}, got {actual!r}. The loader binds columns "
                f"positionally, so a renamed/re-ordered column would be read "
                f"against the wrong field."
            )


def _check_value_bounds(field: str, value, row_index: int) -> None:
    """Raise EligibilityValueError if a numeric value is implausible (Fix 6).

    None (an 'NA' cell) is a legitimate null — it is NEVER bounds-checked."""
    if value is None:
        return
    lo, hi = ELIGIBILITY_VALUE_BOUNDS[field]
    if not (lo <= value <= hi):
        raise EligibilityValueError(
            f"{field} out of plausible bounds at data row {row_index}: value "
            f"{value!r} not in [{lo}, {hi}]. (ami_ratio is stored as a FRACTION "
            f"~0.9; a value near percent scale ~91 signals an upstream 100x "
            f"scale flip that would break every AMI comparison.)"
        )


def get_cache_dir() -> Path:
    path = Path(CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(filename: str) -> Path:
    return get_cache_dir() / filename


def download_eligibility_file(force: bool = False) -> Path:
    filename = "NMTC_LIC_Eligibility_2016_2020.xlsb"
    path = _cache_path(filename)
    if path.exists() and not force:
        print(f"Using cached eligibility file: {path}")
        return path
    print("Downloading NMTC eligibility file from CDFI Fund...")
    # Stream to a .part temp and atomically rename on success, so a mid-stream
    # failure can never leave a truncated file at the final cache path (which
    # would make every later run parse-fail on poisoned cache).
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        response = requests.get(CDFI_FUND_LIC_URL_2020, stream=True, timeout=120)
        response.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        tmp.replace(path)
        print(f"Saved to {path}")
        return path
    except requests.exceptions.HTTPError as e:
        tmp.unlink(missing_ok=True)
        status = getattr(e.response, "status_code", None)
        if status == 404:
            reason = "not found (404) — the CDFI Fund file path may have moved"
        elif status == 403:
            reason = "access blocked (403 Forbidden)"
        else:
            reason = f"HTTP {status}"
        raise EligibilityDownloadError(
            f"Failed to download NMTC eligibility file from "
            f"{CDFI_FUND_LIC_URL_2020}: {reason}"
        ) from e
    except requests.exceptions.RequestException as e:
        tmp.unlink(missing_ok=True)
        raise EligibilityDownloadError(
            f"Failed to download NMTC eligibility file from "
            f"{CDFI_FUND_LIC_URL_2020}: connection/DNS/timeout error "
            f"({type(e).__name__}: {e})"
        ) from e


def load_eligibility_table(force: bool = False) -> pd.DataFrame:
    path = download_eligibility_file(force=force)
    if path is None or not path.exists():
        # download_eligibility_file now raises on any download failure, so a
        # missing file here means the download step was skipped and no local
        # copy exists. Fail loud — never substitute demo data (F2).
        raise EligibilityDownloadError(
            f"No eligibility file available at "
            f"{_cache_path('NMTC_LIC_Eligibility_2016_2020.xlsb')} and no download "
            f"was performed."
        )
    print(f"Loading eligibility table from {path}...")
    try:
        if path.suffix == ".xlsb":
            return _load_xlsb_table(path)
        df = pd.read_excel(path, dtype=str)
        return _process_eligibility_table(df)
    except EligibilityDataError:
        raise
    except ImportError:
        # Missing optional engine (e.g. pyxlsb) — its own message is actionable
        # and is a dependency problem, not a corrupt-file problem. Don't mask it.
        raise
    except Exception as e:
        raise EligibilityParseError(
            f"Failed to parse eligibility file {path}: {type(e).__name__}: {e}"
        ) from e


def _load_xlsb_table(path: Path) -> pd.DataFrame:
    """Parse the Aug 2025 CDFI Fund .xlsb file.

    Column layout (0-indexed) confirmed from the Aug-2025b release:
      0  GEOID, 1 Metro/Non-metro, 2 LIC eligible (YES/NO),
      3  Poverty rate %, 5 MFI ratio (decimal), 7 Unemployment rate %,
     13  High migration (YES/NO), 14 Severe distress (YES/NO),
     15  Deep distress (YES/NO)
    """
    try:
        import pyxlsb
    except ImportError:
        raise ImportError(
            "pyxlsb is required to read the CDFI Fund .xlsb file. "
            "Install it with: pip install pyxlsb"
        )

    def _num(v):
        # bool is an int subclass — exclude it so a stray YES/NO never divides.
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    records = []
    with pyxlsb.open_workbook(str(path)) as wb:
        with wb.get_sheet(ELIGIBILITY_XLSB_SHEET) as sheet:
            for i, row in enumerate(sheet.rows()):
                vals = [c.v for c in row]
                if i == 0:
                    # Validate structure BEFORE trusting any positional bind.
                    _validate_xlsb_header(vals)
                    continue
                if not vals[0]:
                    continue

                geoid        = str(vals[0]).strip().zfill(11)
                non_metro    = str(vals[1]).strip().upper() != "METRO"
                lic_elig     = str(vals[2]).strip().upper() == "YES"
                poverty_rate = (_num(vals[3]) / 100) if _num(vals[3]) is not None else None
                ami_ratio    = _num(vals[5])
                unemp_rate   = (_num(vals[7]) / 100) if _num(vals[7]) is not None else None
                high_migr    = str(vals[13]).strip().upper() == "YES"
                severe       = str(vals[14]).strip().upper() == "YES"
                deep         = str(vals[15]).strip().upper() == "YES"

                # Value plausibility (Fix 6) — on the STORED value; None passes.
                _check_value_bounds("poverty_rate", poverty_rate, i)
                _check_value_bounds("ami_ratio", ami_ratio, i)
                _check_value_bounds("unemployment_rate", unemp_rate, i)

                if deep:
                    dlevel = "deep"
                elif severe:
                    dlevel = "severe"
                elif lic_elig:
                    dlevel = "lic"
                else:
                    dlevel = "ineligible"

                records.append({
                    "tract_id":              geoid,
                    "nmtc_eligible":         lic_elig,
                    "distress_level":        dlevel,
                    "poverty_rate":          poverty_rate,
                    "ami_ratio":             ami_ratio,
                    "unemployment_rate":     unemp_rate,
                    "is_non_metro":          non_metro,
                    "is_high_migration_rural": high_migr,
                    "is_nmtc_native_area":   False,
                    "severe_distress":       severe,
                    "deep_distress":         deep,
                })

    # Row-count floor: a degenerate/near-empty parse must raise, not yield an
    # (almost) empty table that would silently mark real tracts "not found".
    if len(records) < ELIGIBILITY_MIN_ROWS:
        raise EligibilitySchemaError(
            f"eligibility .xlsb parsed only {len(records)} data rows, below the "
            f"floor of {ELIGIBILITY_MIN_ROWS} (live file has 85,395). This is a "
            f"degenerate parse, not a usable table."
        )

    df = pd.DataFrame(records).set_index("tract_id")
    print(f"Eligibility table loaded: {len(df):,} census tracts")
    return df


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


def load_sample_table() -> pd.DataFrame:
    """Build the 12-tract synthetic demo table — an EXPLICIT opt-in only.

    WARNING: this is 12 synthetic-vintage tracts for demos, examples, and tests.
    It is NEVER valid for a real NMTC eligibility answer. Before 0.3.4 this table
    was substituted silently whenever a download or parse failed, fabricating
    'ineligible' results for real tracts; that path is gone. Use it only through
    ``load_sample_table()`` or ``NMTCMapper.from_sample()`` when you knowingly
    want demo data with ``data_source == "sample"``.
    """
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


# Backwards-compatible alias: the examples/ notebook imports the private name.
# Kept intentionally so that existing imports keep working after the F4 rename.
_build_sample_table = load_sample_table


# ── Opportunity Zone lookup ───────────────────────────────────────────────────

def load_opportunity_zones(force: bool = False) -> set:
    """
    Load the set of Opportunity Zone census tract IDs.
    Returns a set of 11-digit FIPS codes designated as QOZs.

    Source: CDFI Fund designated-qozs.12.14.18.xlsx (8,764 tracts).
    Sheet "QOZs 14Jun", header on row 5 (index 4),
    tract FIPS in column "Census Tract Number".
    Raises OZDownloadError / OZParseError on any failure — never falls back.
    """
    from nmtcmapper.data.schema import OZ_URL_2018

    filename = "QOZ_Designated_2018.xlsx"
    path = _cache_path(filename)

    if not path.exists() or force:
        # Same atomic .part-then-rename pattern as download_eligibility_file —
        # a mid-stream failure must never poison the final cache path.
        tmp = path.with_suffix(path.suffix + ".part")
        try:
            print("Downloading Opportunity Zone tract list...")
            response = requests.get(OZ_URL_2018, stream=True, timeout=60)
            response.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            tmp.replace(path)
            print(f"Saved to {path}")
        except requests.exceptions.HTTPError as e:
            tmp.unlink(missing_ok=True)
            status = getattr(e.response, "status_code", None)
            if status == 404:
                reason = "not found (404) — the OZ file path may have moved"
            elif status == 403:
                reason = "access blocked (403 Forbidden)"
            else:
                reason = f"HTTP {status}"
            raise OZDownloadError(
                f"Failed to download Opportunity Zone file from {OZ_URL_2018}: {reason}"
            ) from e
        except requests.exceptions.RequestException as e:
            tmp.unlink(missing_ok=True)
            raise OZDownloadError(
                f"Failed to download Opportunity Zone file from {OZ_URL_2018}: "
                f"connection/DNS/timeout error ({type(e).__name__}: {e})"
            ) from e

    try:
        df = pd.read_excel(
            path,
            sheet_name="QOZs 14Jun",
            header=4,       # row 5 is the column header row
            dtype=str,
        )
        # Normalize column names: collapse whitespace/newlines, uppercase
        df.columns = df.columns.str.replace(r"\s+", " ", regex=True).str.strip().str.upper()
        for col in ["CENSUS TRACT NUMBER", "GEOID", "CENSUS_TRACT", "TRACT_ID", "TRACT"]:
            if col in df.columns:
                tracts = set(df[col].dropna().str.strip().str.zfill(11).tolist())
                print(f"Loaded {len(tracts):,} Opportunity Zone tracts")
                return tracts
    except OZDataError:
        raise
    except Exception as e:
        raise OZParseError(
            f"Failed to parse Opportunity Zone file {path}: {type(e).__name__}: {e}"
        ) from e

    # File parsed, but none of the known tract columns were present — fail loud
    # rather than degrade to the 6-tract sample (F3).
    raise OZParseError(
        f"Opportunity Zone file {path} parsed but no tract column was found "
        f"(looked for CENSUS TRACT NUMBER / GEOID / CENSUS_TRACT / TRACT_ID / TRACT)."
    )


def _sample_oz_tracts() -> set:
    """6 known OZ tracts — EXPLICIT opt-in only (used by NMTCMapper.from_sample()).

    As of 0.3.4 this is never reached from a download/parse failure path; OZ
    failures raise OZDownloadError / OZParseError instead of degrading to this set.
    """
    return {
        "17031840100",  # Chicago South Side
        "17031839100",  # Chicago West Side
        "26163518300",  # Detroit
        "36061015900",  # NYC Bronx
        "13121010400",  # Atlanta
        "48113010900",  # Dallas
    }
