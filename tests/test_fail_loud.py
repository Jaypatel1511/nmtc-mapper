"""F2/F3 — fail loud, never fabricate.

Every eligibility/OZ download or parse failure must RAISE a typed error instead
of silently returning a synthetic sample (0.3.3 behavior — see repro evidence in
the 0.3.4 changelog). These are the negative-case tests: under 0.3.3 each returns
a fabricated frame/set; under 0.3.4 each raises.
"""
import pytest
import requests

import nmtcmapper.data.loader as loader
from nmtcmapper.data.loader import load_eligibility_table, load_opportunity_zones
from nmtcmapper import (
    NMTCMapper,
    EligibilityDownloadError, EligibilityParseError,
    OZDownloadError, OZParseError,
)

ELIG_FILENAME = "NMTC_LIC_Eligibility_2016_2020.xlsb"
OZ_FILENAME = "QOZ_Designated_2018.xlsx"


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the loader at an empty cache dir so no real cached file interferes."""
    monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
    return tmp_path


def _block_network(monkeypatch, exc=None):
    def _boom(*a, **k):
        raise exc or requests.exceptions.ConnectionError(
            "simulated blocked egress / DNS failure"
        )
    monkeypatch.setattr(loader.requests, "get", _boom)


# ── Eligibility ───────────────────────────────────────────────────────────────

def test_download_failure_raises(isolated_cache, monkeypatch):
    _block_network(monkeypatch)
    with pytest.raises(EligibilityDownloadError):
        load_eligibility_table(force=True)


def test_download_failure_mapper_constructor_raises(isolated_cache, monkeypatch):
    _block_network(monkeypatch)
    with pytest.raises(EligibilityDownloadError):
        NMTCMapper()


def test_corrupt_file_raises(isolated_cache):
    (isolated_cache / ELIG_FILENAME).write_bytes(b"\x00\x01\x02 not a zip garbage")
    with pytest.raises(EligibilityParseError):
        load_eligibility_table(force=False)


def test_html_error_page_raises(isolated_cache):
    # A 403/404 HTML error page saved under the .xlsb name (a real CDN failure mode).
    (isolated_cache / ELIG_FILENAME).write_bytes(
        b"<!DOCTYPE html><html><body><h1>403 Forbidden</h1></body></html>"
    )
    with pytest.raises(EligibilityParseError):
        load_eligibility_table(force=False)


def test_old_sample_on_failure_now_raises(isolated_cache, monkeypatch):
    """The explicit old-behavior guard: blocked egress raises, and crucially NO
    12-row sample frame is returned in its place."""
    _block_network(monkeypatch)
    sentinel = object()
    returned = sentinel
    with pytest.raises(EligibilityDownloadError):
        returned = load_eligibility_table(force=True)
    # Nothing escaped the raise — in particular, not a fabricated 12-tract frame.
    assert returned is sentinel


# ── Opportunity Zones ─────────────────────────────────────────────────────────

def test_oz_download_failure_raises(isolated_cache, monkeypatch):
    _block_network(monkeypatch)
    with pytest.raises(OZDownloadError):
        load_opportunity_zones(force=True)


def test_oz_parse_failure_raises(isolated_cache):
    (isolated_cache / OZ_FILENAME).write_bytes(b"not a real xlsx \x00\x01 garbage")
    with pytest.raises(OZParseError):
        load_opportunity_zones(force=False)


class _DroppingResponse:
    """Mocks a download whose connection drops mid-stream after one chunk."""
    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=8192):
        yield b"PARTIAL_CONTENT_" * 512
        raise requests.exceptions.ChunkedEncodingError("connection dropped mid-stream")


def test_partial_download_cleanup_and_retry(isolated_cache, monkeypatch):
    """H2: a mid-stream download failure must raise the typed download error AND
    leave nothing at the final cache path (no poisoned partial file, no .part
    temp) so the next attempt re-downloads instead of parse-failing forever."""
    monkeypatch.setattr(loader.requests, "get", lambda *a, **k: _DroppingResponse())
    with pytest.raises(EligibilityDownloadError):
        load_eligibility_table(force=True)
    assert not (isolated_cache / ELIG_FILENAME).exists(), \
        "partial download left a poisoned file at the final cache path"
    assert list(isolated_cache.glob("*.part")) == [], ".part temp file left behind"

    # Second attempt: the mock now succeeds. force=False proves no poisoned
    # cache short-circuits the retry — the loader must actually re-download.
    payload = b"FULL_CONTENT" * 100
    calls = []

    class _GoodResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=8192):
            yield payload

    def _good_get(*a, **k):
        calls.append(1)
        return _GoodResponse()

    monkeypatch.setattr(loader.requests, "get", _good_get)
    path = loader.download_eligibility_file(force=False)
    assert calls, "retry never re-downloaded (a leftover file short-circuited it)"
    assert path == isolated_cache / ELIG_FILENAME
    assert path.read_bytes() == payload
    assert list(isolated_cache.glob("*.part")) == []


def test_oz_partial_download_cleanup_and_retry(isolated_cache, monkeypatch):
    """H2, OZ twin — mid-stream drop raises OZDownloadError with a clean cache,
    then a successful retry re-downloads and the full load works end-to-end."""
    import io
    import openpyxl

    monkeypatch.setattr(loader.requests, "get", lambda *a, **k: _DroppingResponse())
    with pytest.raises(OZDownloadError):
        load_opportunity_zones(force=True)
    assert not (isolated_cache / OZ_FILENAME).exists(), \
        "partial OZ download left a poisoned file at the final cache path"
    assert list(isolated_cache.glob("*.part")) == [], ".part temp file left behind"

    # Retry serves a valid OZ workbook -> construction works end-to-end.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "QOZs 14Jun"
    for _ in range(4):            # junk rows 1-4; header on row 5 (index 4)
        ws.append([""])
    ws.append(["Census Tract Number"])
    ws.append(["17031840100"])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()

    class _GoodResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=8192):
            yield data

    monkeypatch.setattr(loader.requests, "get", lambda *a, **k: _GoodResponse())
    oz = load_opportunity_zones(force=False)
    assert oz == {"17031840100"}
    assert list(isolated_cache.glob("*.part")) == []


def test_oz_missing_tract_column_raises(isolated_cache):
    """A structurally-valid xlsx whose tract column is absent must raise, not
    degrade to the 6-tract sample (0.3.3 loader.py:272)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "QOZs 14Jun"
    for _ in range(4):            # junk rows 1-4; header is on row 5 (index 4)
        ws.append(["", "", ""])
    ws.append(["WRONG_COLUMN", "OTHER"])   # header row, no tract column
    ws.append(["17031840100", "x"])        # a data row
    wb.save(isolated_cache / OZ_FILENAME)
    with pytest.raises(OZParseError):
        load_opportunity_zones(force=False)
