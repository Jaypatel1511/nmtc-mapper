# Changelog

All notable changes to nmtc-mapper are documented here.

## [0.4.0] — 2026-07-16

Fail-loud + tri-state eligibility. **This release contains breaking changes** —
functions that used to return a value now raise, and `nmtc_eligible` becomes
`Optional[bool]`. Per 0.x semver, breaking changes ship in a minor.

### Breaking
- **`nmtc_eligible` is now tri-state `Optional[bool]`.** `True` = verified
  eligible, `False` = verified ineligible (the table explicitly says NO),
  `None` = **INDETERMINATE** (geocode no-match, or a tract absent from the
  ~85k-tract universe). A `None` verdict must never be read as a falsy
  "ineligible" — an indeterminate result rendered as `False` is a fabricated
  VERIFIED INELIGIBLE. `distress_level` gains a `"unknown"` value and
  `EligibilityResult` gains a `tract_found` field and an `eligibility_status`
  property (verified-eligible / verified-ineligible / not-found / geocode-failed).
- **The geocoder no longer collapses every failure into `None`.**
  `geocode_address` (and the async `_geocode_single_async`) now:
  - raise `GeocoderTransportError` on transport/HTTP-status/decode failure after
    retries (403 / 5xx / timeout / connection / bad-JSON, each with a
    distinguishable message naming the address);
  - raise `AmbiguousAddressError` when an address matches multiple **different**
    census tracts (matches that all agree on one tract still succeed);
  - return `None` **only** for a genuine no-match (HTTP 200, zero matches).
- **`check_tract` / `check_address` lookup-miss now indeterminate.** An absent
  tract yields `nmtc_eligible=None`, `distress_level="unknown"`, metrics `None`,
  `tract_found=False` — not `False`/`"ineligible"`. `check_address` on a genuine
  geocode no-match yields the same with `geocode_success=False`; typed geocoder
  errors propagate rather than being swallowed into a result.
- **`enrich_dataframe` carries the tri-state** (absent tract → `None`/`"unknown"`,
  not `False`) and adds an additive `eligibility_status` column. `eligible_count`
  no longer counts indeterminate rows as ineligible and reports an
  `indeterminate` tally.

### Added
- **New typed exceptions, all under `NMTCMapperError`:**
  `EligibilitySchemaError`, `EligibilityValueError`, `GeocoderError` →
  {`GeocoderTransportError`, `AmbiguousAddressError`}.
- **Schema validation at load (.xlsb path).** Before any row is trusted the
  loader checks the column count (16), the header strings at every
  positionally-bound index (normalized: whitespace-collapsed, casefolded), and a
  row-count floor — raising `EligibilitySchemaError` naming the offending index,
  expected, and actual. The positional bind can no longer read a poverty rate out
  of the MFI slot silently.
- **Value plausibility bounds.** Parsed numerics are range-checked against bounds
  derived from all 85,395 live rows: `poverty_rate` and `unemployment_rate`
  (stored ÷100) in `[0, 1]`; `ami_ratio` (stored as a FRACTION) in `[0, 10]` — the
  upper bound clears the real max (5.162) yet trips an upstream percent-scale flip
  (0.9127 → 91.27), a silent 100× error in every AMI comparison. An `'NA'` cell
  remains a legitimate null and is never bounds-checked.
- **`LICENSE`** (MIT) added.

### Fixed
- `summary()` renders an indeterminate result distinctly (inline qualifier on the
  NMTC Eligible line) instead of the fabricated `❌ NO`.
- `loader.py` module docstring corrected: the table is the FULL universe
  (35,167 eligible + 50,228 ineligible), not "all eligible census tracts".
- **Async batch geocoding was 100% broken and is now fixed (C-1).**
  `_batch_geocode_async` wrapped every coroutine in `create_task` inside an
  `as_completed` loop that discarded the results, then `gather()`-ed the same
  coroutine objects — re-awaiting an already-driven coroutine raised
  `RuntimeError: cannot reuse already awaited coroutine`. Every
  `enrich(address_col=)` / `geocode_batch(use_async=True)` call on ≥2 addresses
  raised. Each coroutine is now awaited exactly once via a single `gather`.
- **A geocoder error aborts the whole batch.** `_batch_geocode_async` calls
  `gather` **without** `return_exceptions`, so a transport/ambiguity failure in
  any one address raises its typed `GeocoderError` and aborts the entire batch.
  This is deliberate, not a regression: it replaces the pre-0.4.0 silent per-row
  `None`, which downstream became a fabricated **verified-ineligible**. Losing
  time to a re-run is strictly better than losing truth. This is not a feature —
  per-row failure capture (continue the batch, mark only the failed rows
  indeterminate) is planned for **0.4.1**.
- **No `nest_asyncio`.** `geocode_batch` previously reached for `nest_asyncio`
  when called inside a running event loop (e.g. Jupyter) — an **undeclared
  dependency** absent from `Requires-Dist`, working only off an ambient install.
  It now detects a running loop and falls back to the synchronous path with a
  `RuntimeWarning` (identical results, only slower); no new dependency.
- **`EligibilityResult.eligibility_status` no longer fabricates
  `verified-ineligible` for an indeterminate result (M-4).** With
  `nmtc_eligible=None` and `tract_found` defaulted `True`, the property fell
  through its falsy branch and returned `verified-ineligible`; it now guards
  `is None` first, as `summary()` already did.

## [0.3.4] — 2026-07-11

### Fixed — fail loud, never fabricate (this is a correctness release)
- **Silent sample-data substitution removed from every failure path.** In
  0.1.0–0.3.3 the loader silently substituted a 12-tract synthetic sample dataset
  on ANY eligibility download or parse failure, and a 6-tract OZ sample on ANY OZ
  download or parse failure. Results computed in that state were **fabricated** —
  an eligibility check against a real tract could return a false "ineligible"
  (the tract simply wasn't in the 12-row sample), and no signal ever reached the
  caller. Five distinct fabrication paths are now killed:
  1. eligibility download failure (`loader.py` download step) — was `return None`
     → 12-tract sample; now raises `EligibilityDownloadError`.
  2. eligibility missing-file / download-skipped branch — was 12-tract sample;
     now raises `EligibilityDownloadError`.
  3. eligibility parse failure (corrupt bytes, HTML error page, bad zip) — was
     12-tract sample; now raises `EligibilityParseError`.
  4. OZ download failure — was 6-tract sample; now raises `OZDownloadError`.
  5. OZ parse failure (corrupt file **or** missing tract column) — was 6-tract
     sample; now raises `OZParseError`.

### Added
- **Typed exception hierarchy** (`nmtcmapper/exceptions.py`), exported from the
  package top level:
  `NMTCMapperError` → `EligibilityDataError` → {`EligibilityDownloadError`,
  `EligibilityParseError`}, and `OZDataError` → {`OZDownloadError`,
  `OZParseError`}. Messages name the URL attempted and distinguish access-blocked
  (403 / connection / DNS / timeout) from not-found (404) from parse failure, and
  chain the original exception (`raise ... from e`). Catch at any level:
  `except NMTCMapperError` for anything, or a specific leaf.
- **Explicit sample mode.** `_build_sample_table()` is promoted to the public
  `load_sample_table()` (the underscore name is kept as an alias for the existing
  notebook import), and `NMTCMapper.from_sample()` constructs a mapper on the 12
  sample tracts + 6 OZ sample tracts with **zero network calls**. Sample data is
  now an opt-in demo path only — never a runtime fallback.
- **Provenance marker.** Every mapper carries a `data_source` attribute
  (`"cdfi_fund"` for the real constructor, `"sample"` for `from_sample()`),
  surfaced in `repr(mapper)`, so downstream code can assert it never shipped a
  demo answer as real.

### Known issues
- **Fabrication moves downstream, not gone from the ecosystem.** The flagship
  `nmtc-application-builder` adapter (`nmtc_mapper_adapter.py`) wraps mapper
  construction in a bare `except Exception` and substitutes its own 20-tract
  `_FALLBACK_ELIGIBILITY`. Now that this package raises typed errors instead of
  fabricating, that adapter will catch them and fabricate in its place — until
  the adapter is fixed in a separate cycle (catch the typed errors, surface them
  honestly, and remove both the `redirect_stdout` suppression and the
  geocode-failure fabricated-positive). No change is made to that repo here.

  > **Correction (0.4.0, 2026-07-16):** the claim above that the flagship adapter
  > "will catch them and fabricate in its place" was true only *before* the
  > adapter's 1.1.5 release. As of `nmtc-application-builder` 1.1.5 the adapter no
  > longer fabricates — it catches the typed errors and surfaces them honestly,
  > and the `redirect_stdout` suppression and geocode-failure fabricated-positive
  > are gone. The note above is retained for history but **no longer describes
  > current behavior**; it should not be read as an ongoing accusation against a
  > package that is already fixed.
- **Out of scope, deferred to 0.3.5:** the geocoder failure-swallow in
  `geocoder/census.py`, and schema/column-shift validation of the CDFI Fund file.
  A geocode failure or an unknown/malformed tract ID still returns a normal result with
  `nmtc_eligible=False` / `distress_level="ineligible"` rather than raising — only
  `geocode_success=False` distinguishes it, and `enrich()` output carries no such flag.
  Treat "ineligible" as unverified unless `geocode_success` is True and the tract was found.

  > **Resolved (0.4.0):** both were fixed in 0.4.0, not 0.3.5 — the geocoder now
  > raises typed `GeocoderTransportError` / `AmbiguousAddressError`, a lookup miss
  > is `None`/`"unknown"` (never `False`/`"ineligible"`), and `enrich()` carries an
  > `eligibility_status` column.

## [0.3.3] — 2026-06-23

> **Correction (2026-07):** the "publishes to PyPI via an OIDC Trusted Publisher" line in the
> 0.3.3 entry below described the *intended* pipeline; 0.3.3 was actually published manually
> with twine, no attestations. The OIDC pipeline first runs for 0.3.4.

### Changed
- **`__version__` is now derived from installed package metadata** via
  `importlib.metadata.version("nmtc-mapper")` instead of a hardcoded string.
  This fixes a drift where the shipped wheel reported `__version__ == "0.1.0"`
  while the distribution had been bumped to `0.3.2` — `pyproject.toml` is now
  the single authoritative source of the version.
- **`setup.py` reduced to a build shim** — the stale `version="0.3.0"` pin and
  the duplicate dependency list were removed; all metadata now lives in
  `pyproject.toml`.

### Added
- **CI / release infrastructure** — `ci.yml` (test matrix on Python 3.9–3.12,
  all actions SHA-pinned) and a tag-triggered `release.yml` that verifies the
  tag matches `pyproject.toml`, builds the wheel, tests the installed wheel in a
  fresh venv, and publishes to PyPI via an OIDC Trusted Publisher (no API token).

No behavioral or API change — this is a hygiene-only release.

## [0.3.2] — 2026-05-14

### Fixed
- **OZ download URL** — The original URL (`cdfifund.gov/sites/cdfi/files/2018-06/
  QOZ_Tracts_List_Formatted_July2018.xlsx`) returned HTTP 404, causing every
  cold install to fall back to a 6-tract sample and flag no real project as an
  Opportunity Zone.  Updated to the canonical CDFI Fund file at
  `cdfifund.gov/system/files/documents/designated-qozs.12.14.18.xlsx`.
- **OZ xlsx parse logic** — The new file uses sheet name `"QOZs 14Jun"`, has a
  preamble so the actual column header is on row 5 (index 4), and names the
  tract column `"Census Tract Number"` rather than `"GEOID"` / `"TRACT"`.
  Updated `load_opportunity_zones()` to pass `sheet_name` and `header=4`, and
  added `"CENSUS TRACT NUMBER"` as the first candidate in the column search.
- **openpyxl floor raised to `>=3.1.0`** — current pandas requires this minimum
  to read the OZ xlsx; the previous floor of `>=3.0.0` allowed installs that
  silently failed to parse the file.

## [0.3.1] — 2026-05-14

### Fixed
- **CDFI Fund download URL** — The Aug 2025 CDFI Fund site update moved the
  NMTC eligibility file to a new path and changed the format from `.xlsx` to
  `.xlsb`. The previous URL returned HTTP 404, causing every fresh install to
  silently fall back to the 12-tract sample dataset and classify all real tracts
  as ineligible.

### Added
- **`.xlsb` format support** — Added `pyxlsb>=1.0.0` as a dependency and a new
  `_load_xlsb_table()` parser in `data/loader.py`. The loader now detects file
  format by extension and routes accordingly; the legacy `.xlsx` path is
  preserved as a fallback.
- **CDFI Fund pre-computed distress flags** — The Aug 2025 file ships its own
  `Severe distress` and `Deep distress` YES/NO columns computed by CDFI Fund
  staff. `_load_xlsb_table()` reads these directly instead of recomputing from
  raw thresholds, keeping classification consistent with official CDFI Fund
  determinations.

## [0.3.0] — 2025-04-XX

- Added Opportunity Zone overlay flag (`is_opportunity_zone`) on all results.
- 27/27 tests passing.

## [0.2.1] — 2025-XX-XX

- Published to PyPI.

## [0.2.0] — 2025-XX-XX

- Initial public release with `check_tract`, `check_address`, and `enrich`.
