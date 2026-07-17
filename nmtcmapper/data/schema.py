"""
Column mappings, eligibility thresholds, and constants for NMTC eligibility.
Based on 2016-2020 ACS data — mandatory for QLICIs closed on or after Sept 1, 2024.
Source: https://www.cdfifund.gov/research-data
"""

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
DEEP_POVERTY_THRESHOLD         = 0.40   # >= 40% poverty rate
DEEP_AMI_THRESHOLD             = 0.50   # <= 50% of AMI
DEEP_UNEMPLOYMENT_MULTIPLIER   = 2.0    # >= 2x national unemployment rate

# National unemployment rate benchmark (2016-2020 ACS)
NATIONAL_UNEMPLOYMENT_RATE     = 0.057  # 5.7%

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
    0:  "2020 Census Tract Number FIPS code. GEOID",
    1:  "OMB Metro/Non-metro Designation, March 2020 (OMB Bulletin No. 20-01)",
    2:  "Does Census Tract Qualify For NMTC Low-Income Community (LIC) on Poverty or Income Criteria?",
    3:  "Census Tract Poverty Rate % (2016-2020 ACS)",
    5:  "Census Tract Percent of Benchmarked Median Family Income (%) 2016-2020 ACS",
    7:  "Census Tract Unemployment Rate (%) 2016-2020",
    13: "High Migration County Low-Income Community Census Tract",
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
