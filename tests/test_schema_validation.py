"""Fix 5 (schema validation at load) + Fix 6 (value plausibility bounds), 0.4.0.

The live .xlsb path binds columns POSITIONALLY and skips the header blind, so a
re-ordered/renamed column or a degenerate parse is read silently against the
wrong fields. These tests drive a MOCKED pyxlsb workbook so they run offline.

FIXTURE REALISM IS LOAD-BEARING — this fixture mirrors the real live file (the
July-2026 re-publish of the Aug-2025b release, at the same URL):
  * exactly 16 columns, with the real header strings (verified live);
  * poverty & unemployment stored as PERCENTS (19.7, 1.7) — the loader /100s them;
  * ami_ratio (col 5) stored as a FRACTION (0.9127...) even though its header
    says "(%)" — read AS-IS.
The magnitudes must NOT be "simplified"/normalized: a fixture that stored ami as
91.27 or poverty as 0.197 would keep this suite green over exactly the scale-flip
bug Fix 6 exists to catch (the "green over a fabricated grade" failure mode).
"""
import re
from pathlib import Path

import pandas as pd
import pytest

import nmtcmapper.data.loader as loader
from nmtcmapper.data.loader import _load_xlsb_table
from nmtcmapper.data.schema import (
    ELIGIBILITY_XLSB_EXPECTED_HEADERS,
    SEVERE_POVERTY_THRESHOLD, SEVERE_AMI_THRESHOLD,
    SEVERE_UNEMPLOYMENT_MULTIPLIER,
    DEEP_POVERTY_THRESHOLD, DEEP_AMI_THRESHOLD,
    DEEP_UNEMPLOYMENT_MULTIPLIER,
    NATIONAL_UNEMPLOYMENT_RATE,
)
from nmtcmapper.exceptions import EligibilitySchemaError, EligibilityValueError

# The real 16-column header row, verified against the live file (July-2026
# re-publish). Indices 2 and 13 were renamed by the CDFI Fund in place; the
# superseded Aug-2025b strings are kept below as SUPERSEDED_HEADER_2025B so the
# suite can prove the pin MOVED rather than widened to accept both.
LIVE_HEADER = [
    "2020 Census Tract Number FIPS code. GEOID",
    "OMB Metro/Non-metro Designation, March 2020 (OMB Bulletin No. 20-01)",
    "Does Census Tract Qualify For NMTC Low-Income Community (LIC) on Poverty or Income Criteria or High Migration Rural Census Tract?",
    "Census Tract Poverty Rate % (2016-2020 ACS)",
    "Does Census Tract Qualify on Poverty Criteria>=20%?",
    "Census Tract Percent of Benchmarked Median Family Income (%) 2016-2020 ACS",
    "Does Census Tract Qualify on Median Family Income Criteria<=80%?",
    "Census Tract Unemployment Rate (%) 2016-2020",
    "County Code",
    "State Name",
    "County Name",
    "Census Tract Unemployment to National Unemployment Ratio ",
    "Population for whom poverty status is determined 2016-2020 ACS",
    "High Migration Rural County Low-Income Community Census Tract",
    "Severe distress=LIC AND (Poverty>30%; MFI<=60%;Unemployment>=1.5)",
    "Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)",
]

# The two header strings as published in the Aug-2025b release, superseded by
# the July-2026 re-publish at the SAME URL. Pinned here so a regression that
# reverted the constants would fail loudly instead of silently.
SUPERSEDED_HEADER_2025B = {
    2:  "Does Census Tract Qualify For NMTC Low-Income Community (LIC) on Poverty or Income Criteria?",
    13: "High Migration County Low-Income Community Census Tract",
}


def make_row(geoid, *, metro="Metro", lic="NO", poverty=13.7, mfi=0.9,
             unemp=2.1, highmig="NO", severe="NO", deep="NO"):
    """A 16-column data row matching the live layout. poverty/unemp are PERCENTS,
    mfi is a FRACTION — as in the real file. Unread indices carry realistic
    placeholders so the row shape is honest."""
    return [
        geoid, metro, lic, poverty,
        "NO",                    # 4  poverty>=20% flag (unread)
        mfi,                     # 5  MFI ratio, FRACTION
        "NO",                    # 6  MFI<=80% flag (unread)
        unemp,                   # 7  unemployment %, PERCENT
        "01001",                 # 8  county code (unread)
        " Alabama",              # 9  state (unread)
        " Autauga County",       # 10 county (unread)
        0.3888,                  # 11 unemp ratio (unread)
        1941.0,                  # 12 population (unread)
        highmig, severe, deep,   # 13,14,15
    ]


# The two spec pins, at their REAL live magnitudes.
PIN_INELIGIBLE = make_row("17031030604", metro="Metro", lic="NO",
                          poverty=19.7, mfi=0.9127530539128933, unemp=1.7)
PIN_ELIGIBLE = make_row("01001020200", metro="Metro", lic="YES",
                        poverty=17.0, mfi=0.7360052851794758, unemp=4.0)


# ── mocked pyxlsb plumbing ────────────────────────────────────────────────────

class _FakeCell:
    __slots__ = ("v",)
    def __init__(self, v):
        self.v = v


class _FakeSheet:
    def __init__(self, rows):
        self._rows = rows
    def rows(self):
        for r in self._rows:
            yield [_FakeCell(v) for v in r]
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _FakeWorkbook:
    def __init__(self, sheet_rows):
        self._sheet_rows = sheet_rows
    def get_sheet(self, name):
        return _FakeSheet(self._sheet_rows)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _load(monkeypatch, rows):
    """Parse `rows` (list of full rows incl. header at index 0) through the real
    _load_xlsb_table with pyxlsb mocked."""
    monkeypatch.setattr("pyxlsb.open_workbook", lambda *_a, **_k: _FakeWorkbook(rows))
    return _load_xlsb_table(Path("fake.xlsb"))


def _padding(n):
    """n valid, in-bounds data rows with distinct GEOIDs, to clear the row floor."""
    return [make_row(f"9{i:010d}", lic=("YES" if i % 2 else "NO"),
                     poverty=10.0 + (i % 30), mfi=0.5 + (i % 5) * 0.1, unemp=3.0)
            for i in range(n)]


# ── Fix 5: happy path pins the real magnitudes ────────────────────────────────

def test_happy_path_parses_pins_at_real_magnitudes(monkeypatch):
    rows = [LIVE_HEADER, PIN_INELIGIBLE, PIN_ELIGIBLE] + _padding(1200)
    df = _load(monkeypatch, rows)
    assert len(df) >= 1000

    a = df.loc["17031030604"]
    assert a["nmtc_eligible"] is False or a["nmtc_eligible"] == False
    assert a["distress_level"] == "ineligible"
    assert abs(a["poverty_rate"] - 0.197) < 1e-9          # 19.7% -> 0.197
    # ami stays a FRACTION (~0.9127), NOT 91.27 — read as-is despite the "%" header
    assert abs(a["ami_ratio"] - 0.9127530539128933) < 1e-9
    assert a["severe_distress"] == False and a["deep_distress"] == False

    b = df.loc["01001020200"]
    assert b["nmtc_eligible"] == True
    assert b["distress_level"] == "lic"
    assert abs(b["poverty_rate"] - 0.17) < 1e-9
    assert abs(b["ami_ratio"] - 0.7360052851794758) < 1e-9


# ── Fix 5: column count ───────────────────────────────────────────────────────

def test_wrong_column_count_raises(monkeypatch):
    short_header = LIVE_HEADER[:15]                      # 15 cols, expected 16
    rows = [short_header] + _padding(1200)
    with pytest.raises(EligibilitySchemaError) as ei:
        _load(monkeypatch, rows)
    msg = str(ei.value)
    assert "15" in msg and "16" in msg


# ── Fix 5: header string mismatch (rename) ────────────────────────────────────

def test_header_rename_raises_naming_index(monkeypatch):
    bad = list(LIVE_HEADER)
    bad[5] = "Some Renamed MFI Column"
    rows = [bad] + _padding(1200)
    with pytest.raises(EligibilitySchemaError) as ei:
        _load(monkeypatch, rows)
    assert "5" in str(ei.value)


# ── Fix 5: positional column re-order ─────────────────────────────────────────

def test_header_reorder_raises(monkeypatch):
    """poverty (3) and MFI (5) swapped: a positional bind would silently read
    poverty out of the MFI slot. Header validation must catch it."""
    swapped = list(LIVE_HEADER)
    swapped[3], swapped[5] = swapped[5], swapped[3]
    rows = [swapped] + _padding(1200)
    with pytest.raises(EligibilitySchemaError):
        _load(monkeypatch, rows)


def test_header_whitespace_and_case_insensitive(monkeypatch):
    """Normalization: collapse internal whitespace + casefold. A header that
    differs only by spacing/case must still validate (no false positive)."""
    noisy = list(LIVE_HEADER)
    noisy[0] = "  2020   Census Tract Number FIPS code.   GEOID  ".upper()
    rows = [noisy, PIN_INELIGIBLE] + _padding(1200)
    df = _load(monkeypatch, rows)         # must NOT raise
    assert "17031030604" in df.index


# ── Fix 5: row-count floor ────────────────────────────────────────────────────

def test_near_empty_parse_raises(monkeypatch):
    rows = [LIVE_HEADER, PIN_INELIGIBLE, PIN_ELIGIBLE]   # only 2 data rows
    with pytest.raises(EligibilitySchemaError) as ei:
        _load(monkeypatch, rows)
    assert "2" in str(ei.value)                          # names the actual count


# ── Fix 6: value plausibility bounds ──────────────────────────────────────────

def test_ami_percent_scale_flip_raises(monkeypatch):
    """The headline Fix 6 case: ami_ratio flipped to percent scale (91.27)."""
    bad = make_row("17031030604", lic="NO", poverty=19.7, mfi=91.27, unemp=1.7)
    rows = [LIVE_HEADER, bad] + _padding(1200)
    with pytest.raises(EligibilityValueError) as ei:
        _load(monkeypatch, rows)
    msg = str(ei.value)
    assert "ami_ratio" in msg and "91.27" in msg


def test_poverty_out_of_bounds_raises(monkeypatch):
    bad = make_row("17031030604", poverty=150.0)         # -> scaled 1.5 > 1.0
    rows = [LIVE_HEADER, bad] + _padding(1200)
    with pytest.raises(EligibilityValueError) as ei:
        _load(monkeypatch, rows)
    assert "poverty_rate" in str(ei.value)


def test_unemployment_out_of_bounds_raises(monkeypatch):
    bad = make_row("17031030604", unemp=250.0)           # -> scaled 2.5 > 1.0
    rows = [LIVE_HEADER, bad] + _padding(1200)
    with pytest.raises(EligibilityValueError):
        _load(monkeypatch, rows)


def test_real_max_ami_within_bounds(monkeypatch):
    """The live max ami (5.162) must PASS — a bound tighter than real data would
    break the package on live input."""
    ok = make_row("17031030604", mfi=5.162086747668833)
    rows = [LIVE_HEADER, ok] + _padding(1200)
    df = _load(monkeypatch, rows)                         # must NOT raise
    assert abs(df.loc["17031030604"]["ami_ratio"] - 5.162086747668833) < 1e-9


def test_na_cells_are_legitimate_nulls_not_bounds_errors(monkeypatch):
    """'NA' poverty/ami (1,583 / 2,358 live rows) -> None, and must NOT trip the
    bounds check."""
    na_row = make_row("17031030604", poverty="NA", mfi="NA", unemp=1.7)
    rows = [LIVE_HEADER, na_row] + _padding(1200)
    df = _load(monkeypatch, rows)                         # must NOT raise
    r = df.loc["17031030604"]
    # In a numeric DataFrame column, a missing value is NaN (pandas' null).
    assert pd.isna(r["poverty_rate"])
    assert pd.isna(r["ami_ratio"])


# ── 0.4.2: the July-2026 in-place re-publish ─────────────────────────────────
#
# The CDFI Fund re-published the eligibility .xlsb at the SAME URL in July 2026,
# renaming two headers the loader binds positionally. The guard fired, which is
# what it exists to do. These tests pin the NEW strings and prove the pin moved
# rather than widened — an exact-match guard that learned to accept both spellings
# would no longer be able to detect the next re-publish.

def test_superseded_2025b_headers_now_raise(monkeypatch):
    """The pin MOVED. Feeding the old Aug-2025b header must now raise, at both
    renamed indices. If this test ever passes silently, the guard has been
    widened to tolerate drift."""
    for idx, old in SUPERSEDED_HEADER_2025B.items():
        stale = list(LIVE_HEADER)
        stale[idx] = old
        rows = [stale] + _padding(1200)
        with pytest.raises(EligibilitySchemaError) as ei:
            _load(monkeypatch, rows)
        assert f"column index {idx}" in str(ei.value)


def test_column_2_pin_names_high_migration_rural():
    """Column 2 is no longer 'poverty or income' alone — as of July 2026 it also
    carries High Migration Rural tracts (LIC via <=85% AMI under AJCA 2004 §223).
    The pinned string must say so; this is the semantic change of 0.4.2, and a
    constant that drifted back would change what ``nmtc_eligible`` asserts."""
    pinned = ELIGIBILITY_XLSB_EXPECTED_HEADERS[2]
    assert "High Migration Rural" in pinned
    assert "Poverty or Income Criteria or" in pinned


def test_deep_and_severe_constants_agree_with_pinned_header_definitions():
    """The file states its own distress definitions in the column 14/15 headers.
    Parse them and assert the exported constants match, so the two definitions of
    'distress' in this package can never disagree again (the 0.4.1 defect: the
    header said MFI<=40%/unemp>=2.5 while the constants said 50%/2.0)."""
    sev = ELIGIBILITY_XLSB_EXPECTED_HEADERS[14]
    deep = ELIGIBILITY_XLSB_EXPECTED_HEADERS[15]

    def parse(header):
        pov = float(re.search(r"Poverty>(\d+)%", header).group(1)) / 100
        mfi = float(re.search(r"MFI<=(\d+)%", header).group(1)) / 100
        unemp = float(re.search(r"Unemployment>=([\d.]+)", header).group(1))
        return pov, mfi, unemp

    assert parse(sev) == (SEVERE_POVERTY_THRESHOLD,
                          SEVERE_AMI_THRESHOLD,
                          SEVERE_UNEMPLOYMENT_MULTIPLIER)
    assert parse(deep) == (DEEP_POVERTY_THRESHOLD,
                           DEEP_AMI_THRESHOLD,
                           DEEP_UNEMPLOYMENT_MULTIPLIER)


def test_national_unemployment_rate_matches_cdfi_fund_notes():
    """The file's NOTES sheet, Column L: 'the national unemployment rate, which
    is 5.4 percent.' Verified independently by exact arithmetic over the live
    file: col H / col L == 5.400000 for all 82,107 rows with a non-zero ratio.
    0.4.1 shipped 5.7%, which raised the unemployment bar on every distress
    comparison."""
    assert NATIONAL_UNEMPLOYMENT_RATE == 0.054


def test_schema_error_message_tells_the_user_what_to_do(monkeypatch):
    """H3: when this fires again — and it will, because the Fund re-publishes at
    the same URL — the exception itself must carry the remedy."""
    bad = list(LIVE_HEADER)
    bad[2] = "Does Census Tract Qualify For Something Else Entirely?"
    rows = [bad] + _padding(1200)
    with pytest.raises(EligibilitySchemaError) as ei:
        _load(monkeypatch, rows)
    msg = str(ei.value)
    assert "column index 2" in msg                     # still names the index
    assert "re-publishes" in msg or "re-published" in msg
    assert "upgrade" in msg.lower()                    # what to do
    assert "github.com/Jaypatel1511/nmtc-mapper" in msg
    # It must NOT offer a bypass — there is no safe one.
    assert "disable" not in msg.lower()
    assert "skip" not in msg.lower()


# ── 0.4.2: stale-cache self-heal ─────────────────────────────────────────────
#
# download_eligibility_file() returns the cached copy whenever one exists, and
# the CDFI Fund re-publishes IN PLACE under an unchanged filename. So a user who
# ran 0.4.1 has the superseded file sitting in ~/.nmtcmapper/cache, and simply
# upgrading to 0.4.2 would STILL fail: the new pins would be validated against
# the OLD cached bytes. The upgrade remedy would be advice they had just taken.
# On a schema mismatch against a CACHED file, re-download once and re-validate.
# This does not weaken the guard — the fresh file is validated exactly as
# strictly, and a genuine upstream divergence still raises.

def _warm_cache(monkeypatch, tmp_path, *, cached_rows, fresh_rows):
    """Model a warm cache: the load serves `cached_rows`; a forced download
    replaces them with `fresh_rows`. Returns a state dict counting downloads."""
    cache_file = tmp_path / "NMTC_LIC_Eligibility_2016_2020.xlsb"
    cache_file.write_bytes(b"")                       # exists() -> True
    state = {"rows": cached_rows, "downloads": 0}

    def fake_download(force=False):
        if force:
            state["downloads"] += 1
            state["rows"] = fresh_rows
        return cache_file

    monkeypatch.setattr(loader, "_eligibility_cache_path", lambda: cache_file)
    monkeypatch.setattr(loader, "download_eligibility_file", fake_download)
    monkeypatch.setattr("pyxlsb.open_workbook",
                        lambda *_a, **_k: _FakeWorkbook(state["rows"]))
    return state


def test_stale_cached_file_triggers_one_redownload_then_succeeds(monkeypatch, tmp_path):
    stale = list(LIVE_HEADER)
    stale[2] = SUPERSEDED_HEADER_2025B[2]
    state = _warm_cache(monkeypatch, tmp_path,
                        cached_rows=[stale, PIN_ELIGIBLE] + _padding(1200),
                        fresh_rows=[LIVE_HEADER, PIN_ELIGIBLE] + _padding(1200))
    df = loader.load_eligibility_table()
    assert state["downloads"] == 1          # re-downloaded exactly once
    assert "01001020200" in df.index


def test_redownload_that_still_mismatches_raises_and_does_not_loop(monkeypatch, tmp_path):
    """If the fresh file diverges too, the guard must still fail loud — and must
    not retry forever."""
    stale = list(LIVE_HEADER)
    stale[2] = SUPERSEDED_HEADER_2025B[2]
    diverged = list(LIVE_HEADER)
    diverged[2] = "Does Census Tract Qualify For Some Future Criterion?"
    state = _warm_cache(monkeypatch, tmp_path,
                        cached_rows=[stale] + _padding(1200),
                        fresh_rows=[diverged] + _padding(1200))
    with pytest.raises(EligibilitySchemaError) as ei:
        loader.load_eligibility_table()
    assert state["downloads"] == 1          # exactly one retry, not a loop
    assert "Future Criterion" in str(ei.value)


def test_explicit_force_does_not_retry(monkeypatch, tmp_path):
    """force=True already fetched fresh bytes; a mismatch there is real."""
    diverged = list(LIVE_HEADER)
    diverged[13] = "Some Future High Migration Column"
    state = _warm_cache(monkeypatch, tmp_path,
                        cached_rows=[diverged] + _padding(1200),
                        fresh_rows=[diverged] + _padding(1200))
    with pytest.raises(EligibilitySchemaError):
        loader.load_eligibility_table(force=True)
    assert state["downloads"] == 1          # the caller's own forced download only
