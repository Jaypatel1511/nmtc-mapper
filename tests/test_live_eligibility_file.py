"""@live smoke tests — download and parse the REAL CDFI Fund eligibility file.

0.4.2 exists because the CDFI Fund re-published this file IN PLACE, at the same
URL, with two renamed headers; every live load raised EligibilitySchemaError.
The offline suite mocks pyxlsb, so it can only prove the loader agrees with a
fixture WE wrote — it structurally cannot catch the next in-place re-publish.
Only this module consumes the artifact it certifies.

Network-bound and deselected in CI (`-m "not live"`). Run locally with:

    pytest tests/test_live_eligibility_file.py -m live -v

Not skip-marked: these run whenever `live` is selected, and never otherwise.
"""
import pytest

from nmtcmapper.data.loader import load_eligibility_table
from nmtcmapper.data.schema import (
    ELIGIBILITY_XLSB_EXPECTED_HEADERS,
    DEEP_POVERTY_THRESHOLD, DEEP_AMI_THRESHOLD, DEEP_UNEMPLOYMENT_MULTIPLIER,
    SEVERE_POVERTY_THRESHOLD, SEVERE_AMI_THRESHOLD,
    SEVERE_UNEMPLOYMENT_MULTIPLIER,
)

pytestmark = pytest.mark.live

# ── The parity evidence for 0.6.1, pinned (2026-09-14) ───────────────────────
#
# 0.6.1's central claim — the September-2026 .xlsx yields the same verdict as
# the July-2026 .xlsb for every tract — was measured by
# scripts/verify-column-n-parity.py against a legacy file that CAN NO LONGER BE
# DOWNLOADED (its URL is a 403; there is no second copy). Evidence that lives
# only in a cache is a hostage, not a gate. So the legacy file's identity and
# every invariant derived from it are written here, and the invariants that do
# not need the legacy file are asserted against the CURRENT file below, forever.
#
# Every value was re-derived from the legacy bytes one final time before being
# typed, through the package's own dispatch and parser (the legacy load
# substitutes the July-2026 strings at header indices 13/14/15; nothing else is
# relaxed). Same style and purpose as tests/test_oz2.py's OZ2_PUBLISHED_FIGURES.
LEGACY_XLSB_IDENTITY = {
    "url":    "https://www.cdfifund.gov/system/files"
              "?file=2025-08/NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb",
    "sha256": "3a6f5851b836ba4b8c31aac48b7ededd761dd002a8831ebebb4d69a428772d49",
    "bytes":  4_811_307,
    "container": "xlsb",
    # The July-2026 in-place re-publish of the Aug-2025b release, cached 2026-08-09.
    "column_n_header": "High Migration Rural County Low-Income Community Census Tract",
}

# Invariants of the CDFI Fund 2016-2020 ACS table. Those marked CURRENT hold on
# the September-2026 .xlsx and are gated live below; those marked LEGACY-ONLY
# need the legacy bytes and are gated only by the parity script.
ELIGIBILITY_PUBLISHED_FIGURES = {
    "universe":            85_395,   # CURRENT and LEGACY: rows, identical GEOID sets
    "eligible":            35_335,   # CURRENT and LEGACY: nmtc_eligible True
    "level_deep":           8_061,   # CURRENT and LEGACY: distress_level
    "level_severe":        13_121,
    "level_lic":           14_153,
    "level_ineligible":    50_060,
    "severe_flag":         21_182,   # CURRENT and LEGACY: severe_distress True
    "deep_flag":            8_061,   # CURRENT and LEGACY: deep_distress True
    "hmr_current":          1_318,   # CURRENT: is_high_migration_rural True
    "hmr_legacy":           1_422,   # LEGACY-ONLY
    "hmr_dropped":            104,   # LEGACY-ONLY: legacy True, current False
    "hmr_added":                0,   # LEGACY-ONLY: current True, legacy False (strict subset)
    "hmr_current_mfi_na":      14,   # CURRENT: HMR rows whose ami_ratio is NA
    "verdict_diffs":            0,   # LEGACY-ONLY: nmtc_eligible AND distress_level, all rows
}
# The MFI boundary between the kept 1,318 and the dropped 104 — the measurement
# that says what column N now MEANS (the 45D(e)(5) <= 85% band).
ELIGIBILITY_HMR_MFI_BOUNDARY = {
    "kept_max":     0.849885,   # CURRENT: max ami_ratio over HMR rows (84.99%)
    "dropped_min":  0.857339,   # LEGACY-ONLY: min ami_ratio over the 104 (85.7%)
    "dropped_max":  1.344,      # LEGACY-ONLY (134.4%)
}


def derive_current_figures(table) -> dict:
    """The CURRENT-file invariants, computed from a loaded table — never typed.
    Keys match ELIGIBILITY_PUBLISHED_FIGURES so a mismatch names the figure."""
    lvl = table["distress_level"].value_counts()
    hmr = table[table["is_high_migration_rural"]]
    return {
        "universe":          len(table),
        "eligible":          int(table["nmtc_eligible"].sum()),
        "level_deep":        int(lvl.get("deep", 0)),
        "level_severe":      int(lvl.get("severe", 0)),
        "level_lic":         int(lvl.get("lic", 0)),
        "level_ineligible":  int(lvl.get("ineligible", 0)),
        "severe_flag":       int(table["severe_distress"].sum()),
        "deep_flag":         int(table["deep_distress"].sum()),
        "hmr_current":       len(hmr),
        "hmr_current_mfi_na": int(hmr["ami_ratio"].isna().sum()),
    }


@pytest.fixture(scope="module")
def live_table():
    """The real table, downloaded (or read from the user cache) once."""
    return load_eligibility_table()


def test_live_file_loads_and_has_the_full_universe(live_table):
    """The headline 0.4.2 assertion: the pinned headers match the live file, so
    _validate_xlsb_header does not raise and every row parses."""
    assert len(live_table) == 85_395


def test_live_eligible_count_reflects_the_widened_column_c(live_table):
    """July 2026 widened column C to carry High Migration Rural tracts, taking
    the eligible count from 35,167 to 35,335 (+168).

    Since 0.4.2 the verdict is column C OR column N, so this count no longer
    depends on the widening: if the Fund separates the columns again it stays
    35,335 and only the CHANGELOG's account of *where* the flag lives goes
    stale. A reading of 35,167 here would mean the 168 had left column N too —
    a genuine upstream eligibility change, not a reformatting."""
    assert int(live_table["nmtc_eligible"].sum()) == 35_335


def test_live_high_migration_rural_tracts_are_all_lic(live_table):
    """The semantic content of the widening: every High Migration Rural tract
    is flagged eligible in column C. Under Aug-2025b, 168 of them were not —
    v0.3.1 through v0.4.1 reported those as NOT NMTC eligible, which
    contradicted 26 U.S.C. 45D(e)(5), the paragraph AJCA 2004 sec. 223 added.

    Since 0.4.2 the verdict is column C OR column N, so this assertion holds
    whichever column the Fund publishes the flag in.

    0.6.1: the count is 1,318, not 1,422. The September-2026 file narrowed
    column N to the income-route determination (the 104 dropped are poverty-
    route LICs above 85% MFI); see schema.py at index 13 and CHANGELOG 0.6.1.
    A reading of 1,422 here would mean the Fund had restored the wider column."""
    hmr = live_table[live_table["is_high_migration_rural"]]
    assert len(hmr) == 1_318
    assert bool(hmr["nmtc_eligible"].all())


def test_live_column_n_is_all_non_metro_and_within_the_85_percent_band(live_table):
    """What the September-2026 column N now asserts, measured: every YES is a
    non-metro tract with MFI <= 85% (the 45D(e)(5) band) or MFI = NA. If a
    metro tract or an MFI above 85% ever appears here, the column has changed
    meaning again and `is_high_migration_rural` needs another disclosure."""
    hmr = live_table[live_table["is_high_migration_rural"]]
    assert bool(hmr["is_non_metro"].all())
    above = hmr[hmr["ami_ratio"] > 0.85]
    assert above.empty, above.index.tolist()[:10]


def test_live_column_n_is_an_lic_determination_not_county_membership(live_table):
    """The premise the 0.4.2 verdict rests on: column N flags tracts that ARE
    Low-Income Communities by way of a high migration rural county, not tracts
    that merely sit in one. That is what makes `column C OR column N` safe.

    If the Fund ever repurposed column N to mean bare county membership, OR-ing
    it would start granting LIC status to tracts above 85% MFI — the mirror of
    the defect 0.4.2 fixes. Every column-N tract must therefore satisfy a
    statutory prong: poverty >= 20% (45D(e)(1)(A)), or MFI <= 85% (the
    45D(e)(5) band, which subsumes the ordinary <= 80% test)."""
    hmr = live_table[live_table["is_high_migration_rural"]]
    assert len(hmr) == 1_318

    qualifies = (hmr["poverty_rate"] >= 0.20) | (hmr["ami_ratio"] <= 0.85)
    offenders = hmr[~qualifies]
    assert offenders.empty, (
        "column N flags tracts that meet no LIC prong — it is no longer an LIC "
        f"determination and must not be OR-ed into the verdict: "
        f"{offenders.index.tolist()[:10]}"
    )


def test_live_severe_and_deep_flags_match_the_corrected_thresholds(live_table):
    """Recompute the published distress flags from the published metrics using
    the 0.4.2 constants. The CDFI Fund did NOT recompute columns O/P after
    widening column C, so exactly 20 severe / 3 deep rows disagree — all of them
    newly-LIC High Migration Rural tracts. Anything beyond that means our
    thresholds have drifted from the Fund's definition again.

    These are the numbers for the LIVE (July-2026) file. Against the superseded
    Aug-2025b file, reading LIC from column C alone, the same constants fit with
    ZERO mismatches; the CHANGELOG's "zero mismatches" figure is that one, and
    it does not describe the file this test loads.

    Bounding the disagreement is the point. On this same file, substituting the
    0.4.1 thresholds (MFI<=50%, unemployment>=2.0x) while keeping the corrected
    5.4% divisor disagrees on 5,025 rows, and the 0.4.1 release as shipped
    (those thresholds plus a 5.7% divisor) on 4,420 — either would blow through
    this assertion.
    """
    df = live_table
    ratio = df["unemployment_rate"] / 0.054      # tract rate / national rate

    severe = df["nmtc_eligible"] & (
        (df["poverty_rate"] > SEVERE_POVERTY_THRESHOLD)
        | (df["ami_ratio"] <= SEVERE_AMI_THRESHOLD)
        | (ratio >= SEVERE_UNEMPLOYMENT_MULTIPLIER)
    )
    deep = df["nmtc_eligible"] & (
        (df["poverty_rate"] > DEEP_POVERTY_THRESHOLD)
        | (df["ami_ratio"] <= DEEP_AMI_THRESHOLD)
        | (ratio >= DEEP_UNEMPLOYMENT_MULTIPLIER)
    )

    assert int((severe != df["severe_distress"]).sum()) == 20
    assert int((deep != df["deep_distress"]).sum()) == 3


def test_live_file_reproduces_the_pinned_0_6_1_figures(live_table):
    """The half of the 0.6.1 parity evidence that can be re-run forever.

    Each CURRENT-marked value in ELIGIBILITY_PUBLISHED_FIGURES is re-derived
    from the live table and compared by key, so a failure names the figure
    that moved (red proof: change one pinned value, this names that one).
    Also the two structural relations the release rests on: every HMR tract
    is eligible (what makes `C OR N` safe), and no HMR tract exceeds the 85%
    band (what column N now means). The distress distribution here —
    8,061 / 13,121 / 14,153 / 50,060 — is also the invariant recorded for an
    earlier release; the September file reproduces it exactly."""
    got = derive_current_figures(live_table)
    mismatched = {k: (ELIGIBILITY_PUBLISHED_FIGURES[k], got[k])
                  for k in got if got[k] != ELIGIBILITY_PUBLISHED_FIGURES[k]}
    assert not mismatched, (
        "live file no longer reproduces the pinned 0.6.1 figures "
        f"(pinned, live): {mismatched}"
    )
    hmr = live_table[live_table["is_high_migration_rural"]]
    assert bool(hmr["nmtc_eligible"].all()), "an HMR tract is not eligible"
    kept_max = float(hmr["ami_ratio"].max())
    assert kept_max == pytest.approx(ELIGIBILITY_HMR_MFI_BOUNDARY["kept_max"], abs=5e-7), kept_max
    assert kept_max <= 0.85
    # The pinned boundary must be a boundary: kept max strictly below dropped min.
    assert ELIGIBILITY_HMR_MFI_BOUNDARY["kept_max"] < ELIGIBILITY_HMR_MFI_BOUNDARY["dropped_min"]


def test_live_headers_are_byte_identical_to_the_pins():
    """Read the live header row directly and compare every pinned index. This is
    the check that failed in the field and the one that will fail next time.

    0.6.1: reads through the container dispatch rather than pyxlsb directly, so
    it follows whichever format the Fund publishes; and it locates the header
    the way the loader does (first row with a non-blank column 0 — the
    September-2026 .xlsx has a banner row above it)."""
    from nmtcmapper.data.loader import (
        _normalize_header, download_eligibility_file, _sniff_workbook_format,
        _iter_xlsb_rows, _iter_xlsx_rows,
    )
    from nmtcmapper.data.schema import ELIGIBILITY_HEADER_SEARCH_ROWS

    path = download_eligibility_file()
    fmt = _sniff_workbook_format(path)
    rows = _iter_xlsb_rows(path) if fmt == "xlsb" else _iter_xlsx_rows(path)
    header = None
    for i, vals in enumerate(rows):
        if i >= ELIGIBILITY_HEADER_SEARCH_ROWS:
            break
        if vals and vals[0] not in (None, ""):
            header = vals
            break
    assert header is not None, "no header row in the search window"

    assert len(header) == 16
    for idx, expected in ELIGIBILITY_XLSB_EXPECTED_HEADERS.items():
        assert _normalize_header(header[idx]) == _normalize_header(expected), idx


def test_live_file_is_the_container_the_release_was_verified_against():
    """0.6.1 was verified against an .xlsx. If the Fund flips back to .xlsb the
    loader will read it (that is what the dispatch is for) — but the maintainer
    should know, because every count in the release notes was re-derived from
    the .xlsx and a flip is a re-publish."""
    from nmtcmapper.data.loader import download_eligibility_file, _sniff_workbook_format
    assert _sniff_workbook_format(download_eligibility_file()) == "xlsx"
