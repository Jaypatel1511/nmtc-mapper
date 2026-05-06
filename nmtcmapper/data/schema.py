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
# Source: IRS Notice 2018-48 — 8,764 designated QOZ census tracts
# Made permanent by One Big Beautiful Bill Act (2025), new OZ 2.0 designations
# expected in 2026-2027
OZ_URL_2018 = (
    "https://www.cdfifund.gov/sites/cdfi/files/2018-06/"
    "QOZ_Tracts_List_Formatted_July2018.xlsx"
)

# ── Download URLs ─────────────────────────────────────────────────────────────
CDFI_FUND_LIC_URL_2020 = (
    "https://www.cdfifund.gov/sites/cdfi/files/2024-08/"
    "NMTC_LIC_Eligibility_2016_2020_ACS.xlsx"
)

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
}
