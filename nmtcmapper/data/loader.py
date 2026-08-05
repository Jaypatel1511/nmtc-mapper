"""
Download and cache the CDFI Fund NMTC eligibility file.
Builds a lookup table of the FULL census-tract universe (85,395 tracts: 35,335
eligible + 50,060 ineligible), each carrying an explicit YES/NO LIC flag. A
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


# Appended to every schema-drift message (0.4.2). This guard has now fired in
# the field once: the CDFI Fund re-published the eligibility file at the SAME URL
# in July 2026 with two renamed headers, and every live load failed until the
# pinned constants were updated. When that happens the exception is the only
# thing the user sees, so it has to carry the explanation and the remedy.
#
# Deliberately offers NO bypass. There is no safe one: the loader binds columns
# positionally, so continuing past a header it does not recognize means reading
# eligibility out of an unverified slot — a wrong NMTC answer that looks right.
_DRIFT_REMEDY = (
    "\n\nWhy this happens: the CDFI Fund re-publishes the eligibility file IN "
    "PLACE, at the same URL, without changing the filename — so a new layout can "
    "arrive under a file this package already believed it understood. nmtc-mapper "
    "pins the exact header strings on purpose, and fails here rather than parse a "
    "changed file against stale positions."
    "\n\nWhat to do: upgrade nmtc-mapper — a release that recognizes the new "
    "layout may already exist (pip install --upgrade nmtc-mapper). If you are "
    "already on the latest version, please report this, quoting the mismatch "
    "above: https://github.com/Jaypatel1511/nmtc-mapper/issues"
    "\n\nIf you reached this from a cached copy, a fresh download has already "
    "been attempted automatically and also failed to match, so the live file "
    "genuinely differs from what this release pins."
    "\n\nThere is no supported way to bypass this check. The verdicts it would "
    "let through are not trustworthy."
)


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
            + _DRIFT_REMEDY
        )
    for idx, expected in ELIGIBILITY_XLSB_EXPECTED_HEADERS.items():
        actual = header_vals[idx] if idx < n else None
        if _normalize_header(actual) != _normalize_header(expected):
            raise EligibilitySchemaError(
                f"eligibility .xlsb header mismatch at column index {idx}: "
                f"expected {expected!r}, got {actual!r}. The loader binds columns "
                f"positionally, so a renamed/re-ordered column would be read "
                f"against the wrong field."
                + _DRIFT_REMEDY
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


# The cache filename never changes — and neither does the CDFI Fund's URL when
# they re-publish, which is why a warm cache can hold a superseded layout.
ELIGIBILITY_CACHE_FILENAME = "NMTC_LIC_Eligibility_2016_2020.xlsb"


def _eligibility_cache_path() -> Path:
    return _cache_path(ELIGIBILITY_CACHE_FILENAME)


# Both workbooks this package downloads (.xlsb and .xlsx) are OOXML, i.e. ZIP
# containers, so every legitimate body starts with the ZIP local-file-header
# magic. An HTML page does not.
_ZIP_MAGIC = b"PK\x03\x04"

# Small floor purely against a zero-length or stub body that happened to start
# with the magic. The real content check is the header/row-count validation
# downstream; this is only about never installing obvious garbage as the cache.
_MIN_WORKBOOK_BYTES = 4096


def _validated_workbook_bytes(tmp: Path, url: str) -> None:
    """Raise if `tmp` is not plausibly a workbook. Call BEFORE tmp.replace(path).

    An HTTP 200 carrying an HTML body is the shape a CDN/origin stack serves
    during maintenance, and ``raise_for_status()`` is blind to it: the status is
    200, the stream writes fine, and before 0.4.2 the HTML went straight to
    ``tmp.replace(path)`` and destroyed a good 4.8 MB cache. Every later run then
    served those bytes from cache, failed to parse them, and never re-downloaded
    — the package stayed broken until the user found and deleted the cache
    directory by hand. The download must therefore prove the body is a workbook
    before it is allowed anywhere near the cache path.
    """
    size = tmp.stat().st_size if tmp.exists() else 0
    head = tmp.read_bytes()[:len(_ZIP_MAGIC)] if size else b""
    if head != _ZIP_MAGIC or size < _MIN_WORKBOOK_BYTES:
        preview = tmp.read_bytes()[:80] if size else b""
        raise EligibilityDownloadError(
            f"Download from {url} returned {size:,} bytes that are not an "
            f"Excel workbook (expected a ZIP/OOXML container starting "
            f"{_ZIP_MAGIC!r}, got {head!r}). This is the signature of an HTTP 200 "
            f"carrying an error or maintenance page rather than the file. "
            f"The cached copy has NOT been replaced. First bytes: {preview!r}"
        )


def download_eligibility_file(force: bool = False) -> Path:
    path = _eligibility_cache_path()
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
        # Nothing unvalidated may reach the cache path: replacing a good 4.8 MB
        # workbook with an HTML maintenance page is not recoverable from here.
        try:
            _validated_workbook_bytes(tmp, CDFI_FUND_LIC_URL_2020)
        except EligibilityDownloadError:
            tmp.unlink(missing_ok=True)
            raise
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
    """Load the CDFI Fund eligibility table, preferring the cached copy.

    Stale-cache self-heal (0.4.2): the CDFI Fund re-publishes this file IN PLACE
    under an unchanged filename, so a cache warmed by an earlier release can hold
    a superseded layout. Validating the new pins against those old bytes would
    raise EligibilitySchemaError and tell the user to upgrade — advice they had
    just taken. So a schema mismatch on a CACHED file re-downloads once and
    re-validates. This does NOT weaken the guard: the fresh file is checked just
    as strictly, and a genuine upstream divergence still raises (once, not in a
    loop). An explicit force=True already fetched fresh bytes, so it never
    retries.

    The self-heal covers an UNREADABLE cached file as well as a stale-layout one.
    EligibilityParseError is a sibling of EligibilitySchemaError, not a subclass,
    so catching only the latter left a cached file that cannot be parsed at all
    outside the heal: it raised on every run and never triggered a re-download,
    and the user stayed broken until they deleted ~/.nmtcmapper/cache by hand.
    That is exactly the state a truncated write or (before this release) an
    HTTP-200 HTML body left behind, and the cache is the one thing the package
    can fix for itself. Both are caught on a CACHED file only, and both still
    retry at most once.

    The at-most-once property is structural, not a counter: the handler calls the
    private ``_load_eligibility_table(force=True)``, not this wrapper, so the
    retry cannot itself re-enter the heal.
    """
    served_from_cache = (not force) and _eligibility_cache_path().exists()
    try:
        return _load_eligibility_table(force=force)
    except (EligibilitySchemaError, EligibilityParseError) as e:
        if not served_from_cache:
            raise
        if isinstance(e, EligibilitySchemaError):
            print(
                "Cached eligibility file does not match the expected CDFI Fund "
                "layout. The Fund re-publishes in place, so the cached copy may "
                "be superseded — re-downloading once and re-validating..."
            )
        else:
            print(
                "Cached eligibility file could not be read at all — the cached "
                "bytes are corrupt or are not a workbook. Discarding them and "
                "re-downloading once..."
            )
        return _load_eligibility_table(force=True)


def _load_eligibility_table(force: bool = False) -> pd.DataFrame:
    path = download_eligibility_file(force=force)
    if path is None or not path.exists():
        # download_eligibility_file now raises on any download failure, so a
        # missing file here means the download step was skipped and no local
        # copy exists. Fail loud — never substitute demo data (F2).
        raise EligibilityDownloadError(
            f"No eligibility file available at {_eligibility_cache_path()} and no "
            f"download was performed."
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
            f"\n\nThose bytes are not a readable workbook. If they came from the "
            f"cache, a fresh download has already been attempted automatically "
            f"and the file still would not parse, so the problem is upstream or "
            f"on the network path — not a stale cache. You can delete "
            f"{path.parent} to start clean; nothing in it is user data."
        ) from e


def _load_xlsb_table(path: Path) -> pd.DataFrame:
    """Parse the CDFI Fund .xlsb file (Aug-2025b layout, July-2026 re-publish).

    Column layout (0-indexed), confirmed against the live file:
      0  GEOID, 1 Metro/Non-metro, 2 LIC eligible (YES/NO),
      3  Poverty rate %, 5 MFI ratio (decimal), 7 Unemployment rate %,
     13  High Migration Rural County LIC (YES/NO), 14 Severe distress (YES/NO),
     15  Deep distress (YES/NO)

    THE LIC VERDICT IS COLUMN 2 **OR** COLUMN 13 (0.4.2).
    ------------------------------------------------------------------
    Through 0.4.1 the verdict was column 2 alone. That under-reported 168 tracts
    for the whole life of the .xlsb path (v0.3.1 .. v0.4.1): under the Aug-2025b
    layout, column 2 carried only the poverty and <=80%-MFI criteria, and the
    third statutory LIC route — a tract in a high migration rural county with MFI
    at or below 85% of the applicable area MFI, 26 U.S.C. 45D(e)(5), added by
    section 223 of the American Jobs Creation Act of 2004 (P.L. 108-357) — was
    published only in column 13. The July-2026 re-publish widened column 2 to
    absorb column 13, which is why 0.4.2 reads correctly from column 2 alone.
    That is upstream's choice, not a property of this package, and nothing in the
    loader would detect the Fund separating the two columns again: the header
    guard, the row-count floor and the value bounds all pass on such a file and
    the 168 silently go back to "ineligible". OR-ing column 13 in makes the
    verdict follow the statute rather than upstream's current formatting.

    Column 13 is an LIC DETERMINATION, not bare county membership. Establishing
    that is what makes the OR safe: if column 13 meant only "sits in a high
    migration rural county", OR-ing it would grant LIC to HMR tracts whose MFI
    exceeds 85% — the mirror of the defect being fixed. Three independent checks
    on the live file say it is a determination:
      * Its 1,422 YES tracts sit in 437 counties that together hold 1,883 tracts.
        The other 461 are column-13 NO, so the flag is a strict subset of county
        membership. None of those 461 reaches 20% poverty and only 2 fall in the
        <=85% band (see below).
      * Every one of the 1,422 satisfies a statutory LIC prong: 757 on poverty
        >=20%, 1,084 on MFI <=80%, and the remaining 168 in the (80%, 85%] band
        that 45D(e)(5) opens. Zero fail all prongs.
      * The Fund's own widened column 2 is exactly `col4 OR col6 OR col13`
        (poverty flag, MFI<=80% flag, this column) with zero mismatches across
        all 85,395 rows. OR-ing column 13 reproduces the Fund's own rule.
    The Aug-2025b workbook, whose extra "High migration tracts" sheet the
    re-publish dropped, states the same in prose: its county sub-table is headed
    "High Migration Counties (only Low-Income Community census tracts within
    counties are eligible)", and its tract sub-table lists exactly the 168.

    On the live July-2026 file this OR is a NO-OP: all 1,422 column-13 YES rows
    are already column-2 YES, so the eligible count is 35,335 with and without
    it. It is a floor under the verdict, not a change to it.
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
                poverty_rate = (_num(vals[3]) / 100) if _num(vals[3]) is not None else None
                ami_ratio    = _num(vals[5])
                unemp_rate   = (_num(vals[7]) / 100) if _num(vals[7]) is not None else None
                high_migr    = str(vals[13]).strip().upper() == "YES"
                severe       = str(vals[14]).strip().upper() == "YES"
                deep         = str(vals[15]).strip().upper() == "YES"

                # The LIC verdict is column C **OR** column N, never column C
                # alone. See the block comment above _load_xlsb_table for why
                # column N is an LIC determination and not bare "in a high
                # migration rural county", and why this is a no-op today.
                lic_elig     = (str(vals[2]).strip().upper() == "YES") or high_migr

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

    VINTAGE CAVEAT: these are 2010-based census tracts (OZs were designated in
    2018 on 2010 geography). The geocoder returns 2020 tracts, so ~16% of these
    GEOIDs (1,408 / 8,764) have no 2020 equivalent and will not match — a
    resulting ``is_opportunity_zone=False`` may be a vintage miss, not a real
    "not an OZ". See README "Known Issues".
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
            # Same pre-replace guard as the eligibility download: an HTTP-200
            # HTML body must never overwrite a good cached workbook. (The OZ
            # path has no self-heal, so poisoning here would be permanent —
            # which is why nothing unvalidated may reach tmp.replace().)
            try:
                _validated_workbook_bytes(tmp, OZ_URL_2018)
            except EligibilityDownloadError as e:
                tmp.unlink(missing_ok=True)
                raise OZDownloadError(str(e)) from e
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
