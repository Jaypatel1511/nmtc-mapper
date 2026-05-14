# Changelog

All notable changes to nmtc-mapper are documented here.

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
