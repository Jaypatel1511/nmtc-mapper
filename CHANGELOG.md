# Changelog

All notable changes to nmtc-mapper are documented here.

## [0.4.1] — 2026-07-17

Geocoder vintage alignment — the Connecticut correctness fix.

### Fixed
- **Connecticut addresses no longer fail to resolve.** The geocoder sent
  `vintage=Current_Current`, which tracks the newest TIGER release, while the
  CDFI Fund eligibility table is frozen on **2020 census tracts** (its column-0
  header: "2020 Census Tract Number FIPS code. GEOID"). The two had **drifted
  apart**. When the Census Bureau replaced Connecticut's eight legacy counties
  with nine COG/planning regions (effective with the 2022 ACS), addresses in CT
  began geocoding to COG-based GEOIDs (county FIPS `0911x`–`0919x`) that do not
  exist in the table — the county FIPS is the middle five digits of every tract
  GEOID, so the join could not match. The CDFI Fund continues to use the legacy
  county data for Connecticut (NMTC LIC ACS FAQ, Feb 1 2024, General Q4).

  Effect of the drift: on **0.4.0**, every Connecticut address returned
  `not-found` (indeterminate). On **0.1.0–0.3.4**, before the tri-state fix, the
  same drift produced a fabricated **"ineligible"** verdict for real Connecticut
  tracts. **883 Connecticut tracts (316 eligible)** were affected.

  Example: `765 Asylum Ave, Hartford, CT` geocoded to `09110524600` (Capitol
  Planning Region), absent from the table. It now geocodes to `09003524600`
  (same tract, legacy Hartford County), which is in the table and NMTC-eligible.

- **The fix: `vintage=Census2020_Current`.** The address benchmark stays
  `Public_AR_Current` — current address ranges, so newly built addresses still
  geocode — resolved onto **2020** tract geography, which is what the table
  carries. `Census2020_Census2020` was rejected (it would pin the address
  benchmark to 2020 and fail to geocode anything built since); `Census2010` was
  rejected (it returns 2010 tracts, which the 2020-tract table does not carry —
  e.g. Seattle would return the pre-split `53033007100`).

### Changed
- **Tract basis and geocoder vintage are now bound in one structure**
  (`schema.TRACT_VINTAGE`, a frozen `TractVintage`). Both the loader (which
  validates the downloaded table's column-0 header) and the geocoder (which
  sends `benchmark`+`vintage`) read this single object — not two constants in
  two modules that a future edit could desync. `TractVintage.__post_init__`
  refuses to construct a binding whose geocoder vintage, table header, and basis
  year disagree, so this class of drift cannot silently return. When the CDFI
  Fund ships the 2021-2025 ACS table on a new tract vintage, this one object
  moves and both consumers move with it.
- Sync and async geocoder paths both build their request through the one
  `_geocoder_params` helper, so neither can drift from the table or each other.
- `pyproject.toml`: `authors` metadata added; `live` pytest marker registered so
  network smoke tests are deselected in CI (`-m "not live"`).

### Recon (reported, not acted on)
- Enumerated every county FIPS in the table's 85,395 GEOIDs against the Census
  Bureau's current (2024) county universe. **Connecticut is the only drifted
  state**: the 8 legacy CT counties (`09001`–`09015`) are the only table county
  FIPS that no longer exist, and the 9 CT planning regions (`09110`–`09190`) are
  the only current county FIPS absent from the table. No other state is affected
  this cycle.

### Known Issues
- **`is_opportunity_zone` is unreliable — a `False` may be a vintage miss, not a
  real "not an OZ".** This is a *second* vintage-mismatched join, in a different
  field, of the same class as the Connecticut bug — and it is **pre-existing**:
  0.4.1 neither causes nor worsens it (both `Current_Current` and the new
  `Census2020_Current` return non-2010 tracts, so neither ever aligned with the
  2010-based OZ list).

  The Opportunity Zone list is loaded from the CDFI Fund's Dec 2018 designated-
  QOZ file (`designated-qozs.12.14.18.xlsx`). Opportunity Zones were designated
  in 2018 on **2010 census tracts**, and the designation is legally fixed to
  those tracts. Verified against the Census 2010↔2020 tract crosswalk: **all
  8,764 OZ GEOIDs are 2010 tracts**. The geocoder now returns **2020** tracts,
  and **1,408 of the 8,764 OZ designations (~16%)** have no matching GEOID in the
  2020 tract universe (they split, merged, or were renumbered between 2010 and
  2020). `is_opportunity_zone` compares a 2020 GEOID against the 2010-based list,
  so an address in one of those 1,408 designations reports **"Opportunity Zone:
  No"** — a fabricated negative.

  Interpretation: a **`Yes` is trustworthy** (the GEOID matched a designated OZ);
  a **`No` is not** — it may mean "not an OZ" *or* "OZ designation with no 2020
  GEOID," and the package cannot currently distinguish the two.

  Not fixed here. The honest fix makes `is_opportunity_zone` tri-state
  (`Optional[bool]`: `True` on match, `None` on a vintage miss — a real "no" is
  not knowable from this join), a breaking contract change slated for **0.5.0**,
  together with a design decision about geocoding at two vintages.

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
