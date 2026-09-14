"""0.6.1 — the eligibility loader dispatches on what the file IS, not on what the
URL says it is.

On 2026-09-03 the CDFI Fund replaced the pinned `.xlsb` (a 403 from then on)
with an `.xlsx` at a new `?file=` URL. A Drupal `?file=` URL is not a content
type, and the cache filename is a module constant, so neither can be trusted to
say which parser to use. The loader therefore reads the container: both formats
are OOXML zips, and the one member that differs is `xl/workbook.bin` (.xlsb)
versus `xl/workbook.xml` (.xlsx). Anything else is a named package exception
that quotes the first bytes — before 0.6.1 an `.xlsx` fed to the pyxlsb-only
reader died with a bare `KeyError: "There is no item named
'xl/_rels/workbook.bin.rels' in the archive"`, which is not an error a user can
act on.

`.xlsb` support is KEPT, not replaced: a future flip back must not need another
emergency release. The `.xlsb` row-reading path stays covered by the mocked-
pyxlsb suite in test_schema_validation.py; this module proves the container
sniff on both formats and the `.xlsx` path end-to-end on real bytes.

THE .xlsb COVERAGE GAP, STATED WHERE A MAINTAINER WILL HIT IT. This suite
proves the `.xlsb` container SNIFF on a synthetic OOXML zip (a `PK` archive
holding `xl/workbook.bin`) and the `.xlsb` ROW PARSE against a mocked pyxlsb.
No test reads real `.xlsb` bytes through pyxlsb: the only real `.xlsb` the
package has ever read is the legacy CDFI Fund file, which can no longer be
downloaded, and neither LibreOffice nor Excel automation will write an `.xlsb`
fixture on the release machine (tried, 2026-09-13). Real `.xlsb` bytes are
exercised only by scripts/verify-column-n-parity.py, which needs that legacy
file. **If the Fund flips back to `.xlsb`, the pyxlsb path ships untested
against real bytes** — run `pytest tests -m live` against the new file before
tagging, because that is the first time the path meets them.
"""
import zipfile
from pathlib import Path

import openpyxl
import pytest

import nmtcmapper.data.loader as loader
from nmtcmapper.data.loader import (
    _sniff_workbook_format, _load_eligibility_workbook, _load_eligibility_table,
)
from nmtcmapper.data.schema import (
    ELIGIBILITY_XLSB_SHEET, ELIGIBILITY_MIN_ROWS, ELIGIBILITY_HEADER_SEARCH_ROWS,
)
from nmtcmapper.exceptions import EligibilityParseError, EligibilitySchemaError
from tests.test_schema_validation import (
    LIVE_HEADER, make_row, _padding, _FakeWorkbook,
)

# The one non-empty cell of the banner row the Fund placed ABOVE the header in
# the September-2026 .xlsx (column N, "Targeted Distressed Areas"). Every other
# cell in that row is empty, including column 0.
BANNER_ROW = [None] * 13 + ["Targeted Distressed Areas", None, None]


def _zip_with(path: Path, members: dict) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return path


def _write_xlsx(path: Path, rows, sheet=ELIGIBILITY_XLSB_SHEET) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def _fixture_rows(n=ELIGIBILITY_MIN_ROWS + 50):
    """Header + n valid rows, with one row of each verdict class up front."""
    return [LIVE_HEADER] + [
        make_row("17031840100", lic="YES", poverty=35.2, mfi=0.41, unemp=12.0,
                 severe="YES", deep="NO"),
        make_row("17031010100", lic="NO", poverty=5.1, mfi=1.62, unemp=3.0),
    ] + _padding(n)


# ── Container sniff ──────────────────────────────────────────────────────────

def test_sniff_xlsb_container(tmp_path):
    p = _zip_with(tmp_path / "anything.xlsx",
                  {"xl/workbook.bin": b"\x00" * 64, "xl/_rels/workbook.bin.rels": b""})
    assert _sniff_workbook_format(p) == "xlsb"


def test_sniff_xlsx_container(tmp_path):
    p = _zip_with(tmp_path / "anything.xlsb",
                  {"xl/workbook.xml": b"<workbook/>", "xl/_rels/workbook.xml.rels": b""})
    assert _sniff_workbook_format(p) == "xlsx"


def test_sniff_html_body_raises_named_error_quoting_first_bytes(tmp_path):
    p = tmp_path / "f.xlsx"
    p.write_bytes(b"<!DOCTYPE html><html><body>403 Forbidden</body></html>")
    with pytest.raises(EligibilityParseError) as ei:
        _sniff_workbook_format(p)
    msg = str(ei.value)
    assert "<!DOCTYPE html>" in msg
    assert "PK" in msg               # says what a workbook WOULD start with


def test_sniff_zip_without_a_workbook_part_raises_naming_both_parts(tmp_path):
    p = _zip_with(tmp_path / "f.xlsx", {"hello.txt": b"not a spreadsheet"})
    with pytest.raises(EligibilityParseError) as ei:
        _sniff_workbook_format(p)
    msg = str(ei.value)
    assert "xl/workbook.bin" in msg and "xl/workbook.xml" in msg
    assert "hello.txt" in msg        # what it DID find, so the user can see it


def test_sniff_empty_file_raises(tmp_path):
    p = tmp_path / "f.xlsx"
    p.write_bytes(b"")
    with pytest.raises(EligibilityParseError):
        _sniff_workbook_format(p)


def test_sniff_zip_magic_over_garbage_raises_not_keyerror(tmp_path):
    """The exact body test_fail_loud.py's CORRUPT_ZIP_BODY uses: right magic,
    nothing readable behind it. Must be the package's error, not zipfile's."""
    p = tmp_path / "f.xlsx"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 6000)
    with pytest.raises(EligibilityParseError):
        _sniff_workbook_format(p)


# ── Dispatch: the filename is ignored, the bytes decide ──────────────────────

def test_xlsb_bytes_under_an_xlsx_name_go_to_the_pyxlsb_reader(tmp_path, monkeypatch):
    p = _zip_with(tmp_path / "NMTC_LIC_Eligibility_2016_2020.xlsx",
                  {"xl/workbook.bin": b"\x00" * 64})
    monkeypatch.setattr("pyxlsb.open_workbook",
                        lambda *_a, **_k: _FakeWorkbook(_fixture_rows()))
    df = _load_eligibility_workbook(p)
    assert bool(df.loc["17031840100", "nmtc_eligible"]) is True
    assert df.loc["17031840100", "distress_level"] == "severe"


def test_xlsx_bytes_under_an_xlsb_name_go_to_the_openpyxl_reader(tmp_path, monkeypatch):
    # If dispatch keyed on the name, pyxlsb would be asked to open this and
    # raise its bare KeyError. Make the pyxlsb path unmistakable if it fires.
    def _never(*_a, **_k):
        raise AssertionError("dispatch chose pyxlsb for an .xlsx container")
    monkeypatch.setattr("pyxlsb.open_workbook", _never)
    p = _write_xlsx(tmp_path / "NMTC_LIC_Eligibility_2016_2020.xlsb", _fixture_rows())
    df = _load_eligibility_workbook(p)
    assert bool(df.loc["17031010100", "nmtc_eligible"]) is False


# ── The .xlsx path end-to-end on real bytes ──────────────────────────────────

def test_xlsx_with_the_funds_banner_row_parses_at_real_magnitudes(tmp_path):
    """The live September-2026 layout: a banner row, THEN the header, then data.
    Values are stored exactly as the Fund stores them (poverty/unemployment as
    percents, MFI as a fraction) and must come out at the loader's scale."""
    p = _write_xlsx(tmp_path / "live.xlsx", [BANNER_ROW] + _fixture_rows())
    df = _load_eligibility_workbook(p)
    assert len(df) == ELIGIBILITY_MIN_ROWS + 52
    row = df.loc["17031840100"]
    assert row["poverty_rate"] == pytest.approx(0.352)
    assert row["ami_ratio"] == pytest.approx(0.41)
    assert row["unemployment_rate"] == pytest.approx(0.12)
    assert bool(row["severe_distress"]) is True
    assert bool(row["deep_distress"]) is False
    assert row["distress_level"] == "severe"


def test_xlsx_without_a_banner_row_also_parses(tmp_path):
    p = _write_xlsx(tmp_path / "flat.xlsx", _fixture_rows())
    assert len(_load_eligibility_workbook(p)) == ELIGIBILITY_MIN_ROWS + 52


def test_xlsx_header_beyond_the_search_window_is_a_schema_error(tmp_path):
    """The banner-row tolerance is bounded. A sheet whose first real row sits
    below the window is a layout this release does not know, and must say so
    rather than scan on."""
    blanks = [[None] * 16 for _ in range(ELIGIBILITY_HEADER_SEARCH_ROWS)]
    p = _write_xlsx(tmp_path / "deep.xlsx", blanks + _fixture_rows())
    with pytest.raises(EligibilitySchemaError) as ei:
        _load_eligibility_workbook(p)
    assert str(ELIGIBILITY_HEADER_SEARCH_ROWS) in str(ei.value)


def test_xlsx_renamed_header_still_trips_the_pin(tmp_path):
    """The re-pinned headers guard the new container exactly as they guarded the
    old one: a rename at a bound index raises before any row is parsed."""
    rows = _fixture_rows()
    hdr = list(rows[0])
    hdr[13] = "High Migration Rural County Low-Income Community Census Tract"  # July-2026 wording
    p = _write_xlsx(tmp_path / "old.xlsx", [BANNER_ROW, hdr] + rows[1:])
    with pytest.raises(EligibilitySchemaError) as ei:
        _load_eligibility_workbook(p)
    assert "index 13" in str(ei.value)


def test_xlsx_missing_data_sheet_raises_naming_the_sheets_present(tmp_path):
    p = _write_xlsx(tmp_path / "wrong.xlsx", _fixture_rows(), sheet="Sheet1")
    with pytest.raises(EligibilityParseError) as ei:
        _load_eligibility_workbook(p)
    assert ELIGIBILITY_XLSB_SHEET in str(ei.value) and "Sheet1" in str(ei.value)


def test_xlsx_lic_verdict_is_column_c_or_column_n(tmp_path):
    """The 0.4.2 verdict rule survives the container change unchanged."""
    rows = _fixture_rows()
    rows.insert(1, make_row("99999999901", lic="NO", poverty=10.0, mfi=0.83,
                            metro="Non-metro", highmig="YES"))
    p = _write_xlsx(tmp_path / "hmr.xlsx", [BANNER_ROW] + rows)
    df = _load_eligibility_workbook(p)
    assert bool(df.loc["99999999901", "nmtc_eligible"]) is True
    assert bool(df.loc["99999999901", "is_high_migration_rural"]) is True


# ── The public load path uses the dispatch ───────────────────────────────────

def test_load_eligibility_table_reads_a_real_xlsx_from_the_cache_path(tmp_path, monkeypatch):
    p = _write_xlsx(tmp_path / "cached.xlsx", [BANNER_ROW] + _fixture_rows())
    monkeypatch.setattr(loader, "download_eligibility_file", lambda force=False: p)
    df = _load_eligibility_table()
    assert len(df) == ELIGIBILITY_MIN_ROWS + 52


def test_cache_filename_no_longer_claims_xlsb():
    """The Fund publishes an .xlsx today. The cache name records that — and the
    loader never trusts it either way (see the dispatch tests above)."""
    assert loader.ELIGIBILITY_CACHE_FILENAME.endswith(".xlsx")
