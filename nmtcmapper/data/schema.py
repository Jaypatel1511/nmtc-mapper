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
#
# 0.4.3, COMMENT ONLY: this block used to read "# >= 30% poverty rate" while the
# deep block below read "# > 40%". Both describe the same kind of prong and the
# Fund states both the same way — strictly greater. The workbook's column-14
# header is "Poverty>30%" and column-15 is "Poverty>40%" (pinned verbatim in
# ELIGIBILITY_XLSB_EXPECTED_HEADERS), and FAQ Q32 (April 2025) states the deep
# criterion as "poverty rates greater than 40%".
#
# The LIC prong above is `>=` and MUST STAY `>=`: §45D(e)(1)(A) defines an LIC
# by a poverty rate "of at least 20 percent". Two different comparisons in one
# file is correct here, not a typo to reconcile. The Fund's own column-4 header
# spells its half out — "Does Census Tract Qualify on Poverty Criteria>=20%?" —
# and it flags YES on all 163 tracts sitting at exactly 20.0%.
#
# CORRECTED IN 0.5.0. Through 0.4.3 `_compute_eligibility` (loader.py) diverged
# from the Fund's criteria in two ways, and the second was the larger one.
#
#   1. It compared poverty with `>=` against BOTH of these constants, so it was
#      marginally over-inclusive at exactly 30.0% / 40.0%.
#      NAME THE BASELINE. "Marginally over-inclusive" is measured against the
#      Fund's published columns 14/15, which are the only YES/NO the boundary
#      rows can be scored against: 21 LIC tracts sit at exactly 30.0% poverty
#      qualifying on poverty alone and the Fund published severe=NO for all 21;
#      13 at exactly 40.0% with deep=NO for all 13.
#   2. It computed severe_distress / deep_distress as the OR of the three prongs
#      with NO AND-LIC term, while the Fund's headers read
#      `Severe distress=LIC AND (...)`. The poverty and MFI prongs imply LIC on
#      their own; the unemployment prong does not. So a tract at >= 1.5x national
#      unemployment with poverty < 20% and AMI > 80% was flagged severe and is
#      NOT severe under the criterion.
#
#      TWO MEASUREMENTS, TWO BASELINES, BOTH CORRECT — AND THEY ARE NOT THE SAME
#      QUANTITY. Both feed the Fund's own metric columns through the shipped rule
#      over the live 85,395 rows; they differ only in what "NOT LIC" is read from,
#      and quoting either without naming its baseline is what makes them look like
#      two different metrics:
#
#        * against the Fund's PUBLISHED LIC column C: 5,197 rows flagged severe
#          or deep while not LIC (751 of them deep). This is the CRITERION
#          baseline — how far the rule departs from the Fund's own definition.
#        * against the SHIPPED RULE'S OWN LIC output: 5,063 (733 deep). This is
#          the EXPERIENCED baseline — what a 0.4.3 user actually saw, since a user
#          reading `severe_distress` read `nmtc_eligible` from the same call.
#
#      The two reconcile exactly through defect (2) below: 134 of the 5,197 (18 of
#      the 751) are rows the shipped rule itself called LIC while the Fund did
#      not, and all 134 sit inside the 932 tracts that rule granted LIC on
#      non-metro status alone. 5,197 - 134 = 5,063; 751 - 18 = 733.
#
#      Either way, EVERY ONE of them is carried by the unemployment prong alone —
#      poverty 0, MFI 0. That 100% is the structural argument as a measurement:
#      poverty >= 30% implies poverty >= 20%, and MFI <= 60% implies MFI <= 80%,
#      so those two prongs cannot fire outside LIC. Unemployment is the only prong
#      with no LIC implication.
#
# 0.5.0 applies `> 30%` / `> 40%` on the two DISTRESS poverty prongs (the LIC
# prong stays `>=`, per the paragraph above) and AND-s LIC into both distress
# columns. That also repairs `distress_level`, which tested deep, then severe,
# and only then nmtc_eligible — so a True in either distress column
# short-circuited before the LIC check was ever consulted.
#
# NO OFFICIAL-PATH VERDICT WAS EVER AFFECTED, before or after: severe/deep on the
# .xlsb path are read from the Fund's published columns 14/15 and are never
# computed here.
SEVERE_POVERTY_THRESHOLD       = 0.30   # Fund criterion: > 30% poverty rate
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
#      85,395 rows OF THE AUG-2025b FILE, reading LIC from column C alone.
#
#      BE PRECISE ABOUT WHICH FILE. That zero does NOT hold on the July-2026
#      re-publish: the Fund widened column C to absorb column N without
#      recomputing columns O/P, so against the live file the same rule mismatches
#      on 3 deep rows (and 20 severe), every one of them among the 168. The rule
#      did not get worse — the published flags stopped agreeing with the
#      published LIC column. Quoting the zero without naming the file overstates
#      the fit on the data this release actually ships against.
#
#      For scale, on the live file: this pair misses 3 deep rows; substituting
#      the 0.4.1 thresholds (mfi<=0.50, ratio>=2.0) while keeping the corrected
#      5.4% divisor misses 5,025; the 0.4.1 release as actually shipped
#      (0.50 / 2.0 / 5.7%) misses 4,420.
# Note the criteria are OR-ed with each other and AND-ed with LIC — the header's
# semicolons read as "or", confirmed by the same fit. No prong is redundant:
# dropping the poverty term alone costs 1,183 rows, the MFI term 1,244, the
# unemployment term 2,839. These are rows LOST FROM THE MODELLED SET (rows the
# three-prong model flags that the two-prong model does not), not the change in
# mismatch count against the published column; read the latter way the same drops
# give 1,186 / 1,247 / 2,836, which is a different quantity and not a discrepancy.
DEEP_POVERTY_THRESHOLD         = 0.40   # Fund criterion: > 40% poverty rate
DEEP_AMI_THRESHOLD             = 0.40   # <= 40% of AMI
DEEP_UNEMPLOYMENT_MULTIPLIER   = 2.5    # >= 2.5x national unemployment rate

# National unemployment rate benchmark (2016-2020 ACS).
#
# CORRECTED IN 0.4.2: 0.4.1 shipped 0.057. The CDFI Fund uses 5.4%, per the
# eligibility file's NOTES sheet, row "Column L. Tract Unemployment to National
# Unemployment Ratio": "the unemployment rate ratio is the ratio between the
# census tract unemployment rate and the national unemployment rate, which is
# 5.4 percent." Measured on the live file: column H divided by column L rounds to
# 5.400000 at six decimal places for all 82,107 rows with a non-zero ratio
# (observed 5.3999997 .. 5.4000003, largest deviation 3.1e-07). It is float
# division of two published, rounded columns, so it is NOT bit-exact — 2,346 of
# the 82,107 quotients equal 5.4 exactly.
# 5.7% raised the bar on every unemployment-prong distress comparison.
NATIONAL_UNEMPLOYMENT_RATE     = 0.054  # 5.4%

# ── CDFI Fund Eligibility File Column Mappings — REMOVED IN 0.5.0 ────────────
# `ELIGIBILITY_FILE_COLUMNS` described the retired .xlsx source and was consumed
# only by `_process_eligibility_table()`, which 0.5.0 deletes as structurally
# unreachable dead code: `path` reaches the parser only from
# `download_eligibility_file()`, which returns only
# `CACHE_DIR / ELIGIBILITY_CACHE_FILENAME`, and that filename is a module
# constant ending `.xlsb` — so the `path.suffix != ".xlsb"` branch could never
# fire. Re-confirmed by execution before deletion: 0 calls on an unmodified
# package, reachable only after rebinding two module-private names, and a literal
# .csv raises EligibilityParseError because the branch called `pd.read_excel`.
#
# The dict also carried `"NATIVE_AREA": "is_nmtc_native_area"` — the only mapping
# anywhere in this package that could ever have set `is_nmtc_native_area=True`.
# That field is dropped in 0.5.0 (no CDFI Fund tract-keyed native-area source
# exists for NMTC), and the mapping went with it rather than being left behind to
# suggest a source that was never reachable.

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
# against the wrong fields. These constants are verified against the live file —
# they were never copied from the retired .xlsx path's column mapping, which
# 0.5.0 deleted with the dead branch that consumed it — and they let the loader
# validate structure before it trusts any row.
ELIGIBILITY_XLSB_SHEET = "2016-2020"
ELIGIBILITY_XLSB_COLUMN_COUNT = 16

# Expected header string at each positionally-bound index the loader actually
# reads (0,1,2,3,5,7,13,14,15). Matched after normalization (collapse internal
# whitespace, casefold).
#
# THE AUTHORITATIVE SOURCE FOR EVERY STRING BELOW IS THE `2016-2020` DATA SHEET'S
# HEADER ROW — never the NOTES sheet. The workbook disagrees with itself: the
# NOTES sheet's "Column C." row spells it "...or RURAL HIGH MIGRATION Census
# Tract?" while the data sheet, whose row-0 cells are the bytes the loader
# actually compares against, reads "...or HIGH MIGRATION RURAL Census Tract?".
# Normalization only collapses whitespace and case, so the swapped-word variant
# is (correctly) rejected. A maintainer refreshing these pins from the NOTES
# sheet would write a string that has never appeared in the data, and every live
# load would fail with a header mismatch that looks like upstream drift. Read the
# header row:
#   with pyxlsb.open_workbook(path) as wb:
#       with wb.get_sheet(ELIGIBILITY_XLSB_SHEET) as sheet:
#           header = [c.v for c in next(iter(sheet.rows()))]
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

# ── Categorical cell-value allowlists (0.5.0) ────────────────────────────────
# THE HEADER GUARD PINS HEADER STRINGS, NOT CELL VOCABULARIES. A re-publish that
# leaves every header byte-identical and changes one cell from `YES` to `Y`
# passes ELIGIBILITY_XLSB_EXPECTED_HEADERS completely — and the July-2026
# in-place re-publish is standing proof that this Fund edits this file at the same
# URL without renaming it. These allowlists are the only guard that can see a
# value-level change.
#
# Direction is why all five categorical columns are guarded rather than one.
# Column 1 parsed as `!= "METRO"`, so an unrecognized value silently became
# `True` — over-inclusive. Columns 2, 13, 14 and 15 parse as `== "YES"`, so an
# unrecognized value silently became `False`: `'Y'` parsed to `False`. That is
# the FABRICATED-NEGATIVE direction, which is the defect 0.5.0 exists to close,
# and column 2 is the LIC verdict itself.
#
# Matched AFTER the loader's existing `.strip().upper()` normalization. Zero rows
# are affected on the live file: all five columns are strict binaries with no
# blanks and no third value across all 85,395 rows (Metro/Non-metro 71,554 /
# 13,841; col C 50,060 NO / 35,335 YES; col N 83,973 / 1,422; col O 64,213 /
# 21,182; col P 77,334 / 8,061).
ELIGIBILITY_METRO_ALLOWED = frozenset({"METRO", "NON-METRO"})
ELIGIBILITY_YESNO_ALLOWED = frozenset({"YES", "NO"})

# Column index -> (human label for the error message, allowed value set).
ELIGIBILITY_XLSB_VALUE_ALLOWLISTS = {
    1:  ("1 (OMB Metro/Non-metro Designation)",        ELIGIBILITY_METRO_ALLOWED),
    2:  ("C (LIC eligibility)",                        ELIGIBILITY_YESNO_ALLOWED),
    13: ("N (High Migration Rural County LIC)",        ELIGIBILITY_YESNO_ALLOWED),
    14: ("O (Severe distress)",                        ELIGIBILITY_YESNO_ALLOWED),
    15: ("P (Deep distress)",                          ELIGIBILITY_YESNO_ALLOWED),
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
