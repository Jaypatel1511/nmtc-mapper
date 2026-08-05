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


# A body with the right ZIP/OOXML magic but no readable workbook inside. Passes
# the 0.4.2 pre-replace download guard (which only proves "this is a container,
# not an HTML page") and fails at parse time — so it exercises the parse path
# rather than the download path.
CORRUPT_ZIP_BODY = b"PK\x03\x04" + b"\x00" * 6000
HTML_ERROR_BODY = (
    b"<!DOCTYPE html><html><head><title>Service Unavailable</title></head>"
    b"<body><h1>Service Unavailable</h1></body></html>"
)


def _serve(monkeypatch, payload):
    """Mock a healthy HTTP 200 that returns `payload`. Counts calls."""
    calls = []

    class _Resp:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=8192):
            for i in range(0, len(payload), chunk_size):
                yield payload[i:i + chunk_size]

    def _get(*a, **k):
        calls.append(1)
        return _Resp()

    monkeypatch.setattr(loader.requests, "get", _get)
    return calls


# ── Eligibility ───────────────────────────────────────────────────────────────

def test_download_failure_raises(isolated_cache, monkeypatch):
    _block_network(monkeypatch)
    with pytest.raises(EligibilityDownloadError):
        load_eligibility_table(force=True)


def test_download_failure_mapper_constructor_raises(isolated_cache, monkeypatch):
    _block_network(monkeypatch)
    with pytest.raises(EligibilityDownloadError):
        NMTCMapper()


def test_corrupt_file_raises(isolated_cache, monkeypatch):
    """A cached file that cannot be parsed raises — after exactly one self-heal
    attempt (0.4.2). Here the fresh copy is corrupt too, so the problem is real
    and must still surface as EligibilityParseError, not be retried forever."""
    (isolated_cache / ELIG_FILENAME).write_bytes(b"\x00\x01\x02 not a zip garbage")
    calls = _serve(monkeypatch, CORRUPT_ZIP_BODY)
    with pytest.raises(EligibilityParseError):
        load_eligibility_table(force=False)
    assert len(calls) == 1, "the parse self-heal must retry exactly once"


def test_html_error_page_raises(isolated_cache, monkeypatch):
    # A 403/404 HTML error page saved under the .xlsb name (a real CDN failure
    # mode). The heal re-downloads once; the origin is still serving HTML, so
    # the pre-replace guard rejects the body before it can overwrite anything.
    (isolated_cache / ELIG_FILENAME).write_bytes(
        b"<!DOCTYPE html><html><body><h1>403 Forbidden</h1></body></html>"
    )
    _serve(monkeypatch, HTML_ERROR_BODY)
    with pytest.raises(EligibilityDownloadError) as ei:
        load_eligibility_table(force=False)
    assert "not an Excel workbook" in str(ei.value)


# ── 0.4.2: an HTTP 200 carrying HTML must never reach the cache ───────────────
#
# raise_for_status() passes on a 200 and the stream writes fine, so before this
# release an Akamai/Acquia-style maintenance page went straight through
# tmp.replace(path) and destroyed a good 4.8 MB cache. EligibilityParseError is
# a sibling of EligibilitySchemaError, not a subclass, so the self-heal never
# caught the resulting failure and never re-downloaded: the package stayed
# broken on every subsequent run, with a healthy network, until the user deleted
# ~/.nmtcmapper/cache by hand.

def test_html_200_does_not_replace_a_good_cache(isolated_cache, monkeypatch):
    """The headline case. A good cached workbook must survive an HTTP-200 HTML
    body byte-for-byte, and the failure must be a typed download error."""
    cache = isolated_cache / ELIG_FILENAME
    good = b"PK\x03\x04" + b"\xab" * 100_000
    cache.write_bytes(good)

    _serve(monkeypatch, HTML_ERROR_BODY)
    with pytest.raises(EligibilityDownloadError) as ei:
        loader.download_eligibility_file(force=True)

    assert cache.read_bytes() == good, "HTML/200 destroyed the cached workbook"
    assert "not an Excel workbook" in str(ei.value)
    assert "has NOT been replaced" in str(ei.value)
    assert list(isolated_cache.glob("*.part")) == [], ".part temp left behind"


def test_html_200_on_a_cold_cache_installs_nothing(isolated_cache, monkeypatch):
    """With no cache to protect, the wrong body must still not be installed —
    otherwise the next run parse-fails on bytes it believes are the real file."""
    _serve(monkeypatch, HTML_ERROR_BODY)
    with pytest.raises(EligibilityDownloadError):
        loader.download_eligibility_file(force=True)
    assert not (isolated_cache / ELIG_FILENAME).exists()
    assert list(isolated_cache.glob("*.part")) == []


def test_poisoned_cache_heals_itself_once(isolated_cache, monkeypatch):
    """A cache already poisoned by a pre-0.4.2 release must recover by itself as
    soon as the origin is healthy — no manual `rm -rf` required.

    The payload here is a container the download guard accepts but pyxlsb cannot
    read, so the heal is driven by the parse path; the point under test is that
    the poisoned bytes are discarded and re-fetched, not the parse outcome."""
    cache = isolated_cache / ELIG_FILENAME
    cache.write_bytes(HTML_ERROR_BODY)          # poisoned: 116 bytes of HTML
    calls = _serve(monkeypatch, CORRUPT_ZIP_BODY)

    with pytest.raises(EligibilityParseError):
        load_eligibility_table(force=False)

    assert len(calls) == 1, "poisoned cache never triggered a re-download"
    assert cache.read_bytes() == CORRUPT_ZIP_BODY, \
        "the poisoned bytes were not replaced by the fresh download"


def test_parse_self_heal_does_not_loop(isolated_cache, monkeypatch):
    """The one-retry cap is structural — the handler calls the private
    _load_eligibility_table(force=True), not the public wrapper, so the retry
    cannot re-enter the heal. Two downloads here would mean it had."""
    (isolated_cache / ELIG_FILENAME).write_bytes(b"garbage, not a workbook")
    calls = _serve(monkeypatch, CORRUPT_ZIP_BODY)
    with pytest.raises(EligibilityParseError):
        load_eligibility_table(force=False)
    assert len(calls) == 1


def test_parse_self_heal_does_not_fire_without_a_cache(isolated_cache, monkeypatch):
    """force=True already fetched fresh bytes, so a failure there is real and
    must not be retried."""
    calls = _serve(monkeypatch, CORRUPT_ZIP_BODY)
    with pytest.raises(EligibilityParseError):
        load_eligibility_table(force=True)
    assert len(calls) == 1, "force=True must not trigger a second download"


def test_failed_heal_preserves_the_cached_bytes(isolated_cache, monkeypatch):
    """A heal attempt that fails at the network layer must leave the cache
    exactly as it found it — a superseded file still beats no file."""
    cache = isolated_cache / ELIG_FILENAME
    superseded = b"PK\x03\x04" + b"\xcd" * 50_000
    cache.write_bytes(superseded)
    _block_network(monkeypatch)
    with pytest.raises(EligibilityDownloadError):
        load_eligibility_table(force=False)
    assert cache.read_bytes() == superseded
    assert list(isolated_cache.glob("*.part")) == []


def test_oz_html_200_does_not_replace_a_good_cache(isolated_cache, monkeypatch):
    """The OZ download has the same tmp.replace() shape and no self-heal at all,
    so poisoning it would be permanent. Nothing unvalidated may land there."""
    cache = isolated_cache / OZ_FILENAME
    good = b"PK\x03\x04" + b"\xef" * 100_000
    cache.write_bytes(good)
    _serve(monkeypatch, HTML_ERROR_BODY)
    with pytest.raises(OZDownloadError) as ei:
        load_opportunity_zones(force=True)
    assert cache.read_bytes() == good
    assert "not an Excel workbook" in str(ei.value)
    assert list(isolated_cache.glob("*.part")) == []


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
    # The payload carries ZIP/OOXML magic and clears the minimum size, because
    # since 0.4.2 the download refuses to install a body that is not a workbook.
    payload = b"PK\x03\x04" + b"FULL_CONTENT" * 500
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
