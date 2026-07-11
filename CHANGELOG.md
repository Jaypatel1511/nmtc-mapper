# Changelog

All notable changes to nmtc-mapper are documented here.

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
- **Out of scope, deferred to 0.3.5:** the geocoder failure-swallow in
  `geocoder/census.py`, and schema/column-shift validation of the CDFI Fund file.

## [0.3.3] — 2026-06-23
<!-- [correction 2026-07: the "publishes to PyPI via an OIDC Trusted Publisher"
     line below describes the *intended* pipeline, but 0.3.3 itself was published
     manually with no attestations. The OIDC Trusted-Publisher pipeline first
     runs for 0.3.4. History is annotated, not rewritten.] -->

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
