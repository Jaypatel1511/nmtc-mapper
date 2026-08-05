"""
Column mappings, eligibility thresholds, and constants for NMTC eligibility.
Based on 2016-2020 ACS data — mandatory for QLICIs closed on or after Sept 1, 2024.
Source: https://www.cdfifund.gov/research-data
"""
from dataclasses import dataclass

# ── Tract-vintage binding: THE single source of truth ─────────────────────────
# The recurring failure class is "geocoder vintage drifts from data vintage".
# The CDFI Fund eligibility table is FROZEN on one census-tract vintage (its
# column-0 header names it), while the Census geocoder's Current_Current vintage
# tracks the newest TIGER release — so the two separate BY DESIGN. Connecticut
# was the first to bite: the Bureau replaced CT's 8 legacy counties with 9
# COG/planning regions effective with the 2022 ACS; the county FIPS is the middle
# 5 digits of every tract GEOID, so the join stopped matching (883 CT tracts,
# 316 eligible, went not-found), while the CDFI Fund keeps using the legacy
# county data for CT (NMTC LIC ACS FAQ, Feb 1 2024, General Q4).
#
# Both the loader (which validates the table's column-0 GEOID header) and the
# geocoder (which sends benchmark+vintage) read THIS ONE object, so the tract
# basis and the geocoder vintage cannot be edited apart in two modules. When the
# CDFI Fund ships the 2021-2025 ACS table on a new tract vintage, edit this ONE
# object — basis_year, geocoder_vintage, and table_geoid_header move together or
# __post_init__ refuses to construct.
@dataclass(frozen=True)
class TractVintage:
    basis_year: int          # census-tract geography the table is built on
    geocoder_benchmark: str  # address ranges — CURRENT so new construction geocodes
    geocoder_vintage: str    # tract geography the geocoder resolves onto (must be basis_year)
    table_geoid_header: str  # the table's column-0 header, proving its tract basis

    def __post_init__(self):
        token = f"Census{self.basis_year}"
        # The geocoder must resolve addresses onto the SAME census-tract geography
        # the table carries. Census2020_Current => 2020 tract geography with
        # current address ranges. A vintage that does not start with this token
        # is exactly the drift this class exists to make impossible.
        if not self.geocoder_vintage.startswith(token + "_"):
            raise ValueError(
                f"geocoder_vintage {self.geocoder_vintage!r} does not resolve onto "
                f"{self.basis_year} census-tract geography (expected a {token}_* "
                f"vintage). The geocoder vintage has drifted from the table's tract "
                f"basis — the Connecticut-class bug."
            )
        # The table's declared geography (its column-0 header) must name the same
        # basis year, so a table download on a different vintage cannot be paired
        # with this geocoder vintage without tripping the loader's header check.
        if str(self.basis_year) not in self.table_geoid_header:
            raise ValueError(
                f"table_geoid_header {self.table_geoid_header!r} does not name the "
                f"{self.basis_year} tract basis. The table's declared geography has "
                f"drifted from basis_year."
            )


# The one binding in force for the 2016-2020 ACS eligibility table.
TRACT_VINTAGE = TractVintage(
    basis_year=2020,
    geocoder_benchmark="Public_AR_Current",
    geocoder_vintage="Census2020_Current",
    table_geoid_header="2020 Census Tract Number FIPS code. GEOID",
)

# ── Eligibility Thresholds ────────────────────────────────────────────────────

# Low-Income Community (LIC) criteria — Section 45D
LIC_POVERTY_RATE_THRESHOLD     = 0.20   # >= 20% poverty rate
LIC_AMI_RATIO_METRO_THRESHOLD  = 0.80   # <= 80% of metro/state AMI
LIC_AMI_RATIO_RURAL_THRESHOLD  = 0.85   # <= 85% of state AMI (high migration rural)

# Severe Distress thresholds
SEVERE_POVERTY_THRESHOLD       = 0.30   # >= 30% poverty rate
SEVERE_AMI_THRESHOLD           = 0.60   # <= 60% of AMI
SEVERE_UNEMPLOYMENT_MULTIPLIER = 1.5    # >= 1.5x national unemployment rate

# Deep Distress thresholds
#
# CORRECTED IN 0.4.2. 0.4.1 shipped DEEP_AMI_THRESHOLD = 0.50 and
# DEEP_UNEMPLOYMENT_MULTIPLIER = 2.0, which are MORE PERMISSIVE than the CDFI
# Fund's own definition and would classify tracts as deeply distressed that the
# Fund does not. Authority, in order of directness:
#   1. The eligibility file's NOTES sheet, row "Column P. Deep Distress":
#      "Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)"
#   2. The same string as the column-15 header on the data sheet (pinned in
#      ELIGIBILITY_XLSB_EXPECTED_HEADERS[15] since 0.4.0 — the package was
#      already carrying the correct definition in one place and the wrong one
#      in another).
#   3. Empirical: LIC AND (poverty>40 OR mfi<=0.40 OR unemp_ratio>=2.5)
#      reproduces the published column-15 flag with ZERO mismatches across all
#      85,395 rows. The 0.4.1 pair (0.50 / 2.0) misses by 5,015 rows.
# Note the criteria are OR-ed with each other and AND-ed with LIC — the header's
# semicolons read as "or", confirmed by the same zero-mismatch fit.
DEEP_POVERTY_THRESHOLD         = 0.40   # > 40% poverty rate
DEEP_AMI_THRESHOLD             = 0.40   # <= 40% of AMI
DEEP_UNEMPLOYMENT_MULTIPLIER   = 2.5    # >= 2.5x national unemployment rate

# National unemployment rate benchmark (2016-2020 ACS).
#
# CORRECTED IN 0.4.2: 0.4.1 shipped 0.057. The CDFI Fund uses 5.4%, per the
# eligibility file's NOTES sheet, row "Column L. Tract Unemployment to National
# Unemployment Ratio": "the unemployment rate ratio is the ratio between the
# census tract unemployment rate and the national unemployment rate, which is
# 5.4 percent." Verified by exact arithmetic on the live file: column H divided
# by column L equals 5.400000 for all 82,107 rows with a non-zero ratio.
# 5.7% raised the bar on every unemployment-prong distress comparison.
NATIONAL_UNEMPLOYMENT_RATE     = 0.054  # 5.4%

# ── CDFI Fund Eligibility File Column Mappings ────────────────────────────────
# Source: 2016-2020 ACS Low-Income Community Eligibility file from cdfifund.gov

ELIGIBILITY_FILE_COLUMNS = {
    "GEOID":                    "tract_id",
    "STATE":                    "state",
    "COUNTY":                   "county",
    "TRACT":                    "tract",
    "POVERTY_RATE":             "poverty_rate",
    "MFI_RATIO":                "ami_ratio",
    "UNEMPLOYMENT_RATE":        "unemployment_rate",
    "NON_METRO":                "is_non_metro",
    "HIGH_MIGRATION_RURAL":     "is_high_migration_rural",
    "LIC_ELIGIBLE":             "lic_eligible_raw",
    "SEVERE_DISTRESS":          "severe_distress_raw",
    "NATIVE_AREA":              "is_nmtc_native_area",
}

# ── Opportunity Zone Data ────────────────────────────────────────────────────
# Source: CDFI Fund "List of designated Qualified Opportunity Zones"
# Updated Dec 14 2018 to add final Puerto Rico tracts (8,764 total).
# Made permanent by One Big Beautiful Bill Act (2025); OZ 2.0 designations
# expected 2027.
# Sheet: "QOZs 14Jun", header row index 4, tract column "Census Tract Number"
OZ_URL_2018 = (
    "https://www.cdfifund.gov/system/files/documents/"
    "designated-qozs.12.14.18.xlsx"
)

# ── Download URLs ─────────────────────────────────────────────────────────────
# Aug 2025 update: CDFI Fund replaced the xlsx with an xlsb at a new path.
# The file now includes pre-computed severe/deep distress flags.
CDFI_FUND_LIC_URL_2020 = (
    "https://www.cdfifund.gov/system/files"
    "?file=2025-08/NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb"
)

# ── Live .xlsb structure (Aug-2025b release) — schema validation (0.4.0) ──────
# The live loader binds columns POSITIONALLY and skips the header blind, so an
# upstream column re-order/rename or a degenerate parse would be read silently
# against the wrong fields. These constants — verified against the live file, NOT
# copied from ELIGIBILITY_FILE_COLUMNS (which describes the retired .xlsx path) —
# let the loader validate structure before it trusts any row.
ELIGIBILITY_XLSB_SHEET = "2016-2020"
ELIGIBILITY_XLSB_COLUMN_COUNT = 16

# Expected header string at each positionally-bound index the loader actually
# reads (0,1,2,3,5,7,13,14,15). Matched after normalization (collapse internal
# whitespace, casefold).
ELIGIBILITY_XLSB_EXPECTED_HEADERS = {
    # Column 0 is the table's tract-basis declaration — read it from the ONE
    # binding, NOT a second literal, so the loader's header check and the
    # geocoder vintage cannot desync (0.4.1).
    0:  TRACT_VINTAGE.table_geoid_header,
    1:  "OMB Metro/Non-metro Designation, March 2020 (OMB Bulletin No. 20-01)",
    # 0.4.2: the CDFI Fund re-published at the SAME URL in July 2026 and WIDENED
    # this column. It now flags High Migration Rural tracts (LIC via <=85% AMI
    # under AJCA 2004 §223) in addition to the poverty/income criteria. The
    # file's own NOTES sheet: "In July 2026, the dataset was reformatted to
    # include High-Migration Rural Census Tracts under COLUMN C. Only formatting
    # changes were made. No eligibility changes were made." That last sentence is
    # true of the STATUTE — those tracts were always LICs — but not of this
    # column: 168 tracts flipped NO->YES here, so `nmtc_eligible` now returns
    # True for 168 tracts where 0.4.1 returned False. See CHANGELOG 0.4.2.
    2:  "Does Census Tract Qualify For NMTC Low-Income Community (LIC) on Poverty or Income Criteria or High Migration Rural Census Tract?",
    3:  "Census Tract Poverty Rate % (2016-2020 ACS)",
    5:  "Census Tract Percent of Benchmarked Median Family Income (%) 2016-2020 ACS",
    7:  "Census Tract Unemployment Rate (%) 2016-2020",
    # 0.4.2: "Rural" inserted in the July-2026 re-publish. Cosmetic — the column's
    # 1,422 YES values are byte-identical to the Aug-2025b release.
    13: "High Migration Rural County Low-Income Community Census Tract",
    14: "Severe distress=LIC AND (Poverty>30%; MFI<=60%;Unemployment>=1.5)",
    15: "Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)",
}

# Row-count floor: the live universe is 85,395 tracts. A degenerate/near-empty
# parse (0, 1, a handful of rows) must raise, not yield an empty table. Set well
# below the real count so a legitimately smaller future vintage is not rejected,
# but far above any degenerate parse.
ELIGIBILITY_MIN_ROWS = 1000

# Value plausibility bounds (Q6 recon over all 85,395 live rows). Applied to the
# STORED value: poverty_rate and unemployment_rate are divided by 100 (fractions
# 0..1); ami_ratio is stored AS-IS as a fraction. A None (from an 'NA' cell) is a
# legitimate null (1,583 poverty / 2,358 ami live) and is NEVER bounds-checked.
#   live poverty_rate scaled: 0.001 .. 1.0    -> [0, 1] (a % cannot exceed 100%)
#   live unemployment scaled: 0.0   .. 0.938  -> [0, 1]
#   live ami_ratio (fraction): 0.0249 .. 5.162 -> [0, 10]; 10 clears the real max
#     with headroom yet trips a percent-scale flip (0.9127 -> 91.27), the silent
#     100x error class this guard exists to catch.
ELIGIBILITY_VALUE_BOUNDS = {
    "poverty_rate":      (0.0, 1.0),
    "unemployment_rate": (0.0, 1.0),
    "ami_ratio":         (0.0, 10.0),
}

# ── Cache ─────────────────────────────────────────────────────────────────────
import os
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".nmtcmapper", "cache")

# ── Census Geocoder API ───────────────────────────────────────────────────────
CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/address"
)
CENSUS_GEOCODER_BATCH_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
)

# ── Distress Levels ───────────────────────────────────────────────────────────
DISTRESS_LEVELS = {
    "deep":     "Deep Distress — highest need, strongest NMTC application score",
    "severe":   "Severe Distress — qualifies for 85% investment commitment",
    "lic":      "Low-Income Community — NMTC eligible",
    "ineligible": "Not NMTC eligible",
    # 0.4.0 tri-state: no verdict was reached (geocode no-match, or a tract
    # absent from the ~85k universe). NOT the same as "ineligible".
    "unknown":  "Indeterminate — eligibility not verified (no match / tract absent)",
}
