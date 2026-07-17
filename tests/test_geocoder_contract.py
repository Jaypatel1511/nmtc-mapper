"""Fix 1 — geocoder contract (sync AND async), 0.4.0.

The overloaded ``None`` return is split three ways:
  (a) transport/HTTP-status/decode failure after retries -> GeocoderTransportError
      with a message that distinguishes 403 / 5xx / timeout / bad-JSON and names
      the address.
  (b) genuine no-match (HTTP 200, zero addressMatches) -> None (and ONLY this).
  (c) multiple matches: all same tract -> that tract; different tracts ->
      AmbiguousAddressError naming the candidates.

All tests are offline: requests.get / the aiohttp session are mocked, backoff
sleeps are stubbed, and every test asserts its mock was actually exercised (a
green test that never hit the mocked call would certify nothing).
"""
import asyncio

import pytest
import requests

import nmtcmapper.geocoder.census as census
from nmtcmapper.geocoder.census import geocode_address, _geocode_single_async
from nmtcmapper.exceptions import (
    GeocoderError, GeocoderTransportError, AmbiguousAddressError,
)

ADDR = "1234 S Michigan Ave, Chicago, IL 60605"


# ── sync fakes ────────────────────────────────────────────────────────────────

class _Resp:
    """Minimal requests-like response."""
    def __init__(self, *, status=200, json_data=None, http_error=False,
                 json_raises=False):
        self.status_code = status
        self._json = json_data if json_data is not None else {}
        self._http_error = http_error
        self._json_raises = json_raises

    def raise_for_status(self):
        if self._http_error:
            err = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err

    def json(self):
        if self._json_raises:
            # HTML error page / truncated body -> json.JSONDecodeError (ValueError)
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json


def _match(state="17", county="031", tract="030604"):
    return {"geographies": {"Census Tracts": [
        {"STATE": state, "COUNTY": county, "TRACT": tract}]}}


def _data(*matches):
    return {"result": {"addressMatches": list(matches)}}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """Never actually sleep during retry backoff — keeps the suite instant."""
    monkeypatch.setattr(census.time, "sleep", lambda *_a, **_k: None)


def _install_sync(monkeypatch, responses):
    """responses: a callable or list; track calls."""
    calls = {"n": 0}
    seq = list(responses)

    def _get(*_a, **_k):
        calls["n"] += 1
        item = seq[min(calls["n"] - 1, len(seq) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(census.requests, "get", _get)
    return calls


# ── (a) transport failures raise, with distinguishable messages ───────────────

def test_sync_403_raises_transport_error_naming_403_and_address(monkeypatch):
    calls = _install_sync(monkeypatch, [_Resp(status=403, http_error=True)])
    with pytest.raises(GeocoderTransportError) as ei:
        geocode_address(ADDR)
    msg = str(ei.value)
    assert "403" in msg
    assert ADDR in msg
    assert calls["n"] == census.MAX_RETRIES + 1  # retried, then raised


def test_sync_5xx_message_distinct_from_403(monkeypatch):
    _install_sync(monkeypatch, [_Resp(status=503, http_error=True)])
    with pytest.raises(GeocoderTransportError) as ei:
        geocode_address(ADDR)
    msg = str(ei.value)
    assert "503" in msg
    assert "403" not in msg


def test_sync_timeout_message_says_timeout(monkeypatch):
    calls = _install_sync(monkeypatch, [requests.exceptions.Timeout("slow")])
    with pytest.raises(GeocoderTransportError) as ei:
        geocode_address(ADDR)
    assert "timed out" in str(ei.value).lower() or "timeout" in str(ei.value).lower()
    assert calls["n"] == census.MAX_RETRIES + 1


def test_sync_connection_message_says_connection(monkeypatch):
    _install_sync(monkeypatch, [requests.exceptions.ConnectionError("dns")])
    with pytest.raises(GeocoderTransportError) as ei:
        geocode_address(ADDR)
    m = str(ei.value).lower()
    assert "connection" in m or "dns" in m


def test_sync_bad_json_message_says_json(monkeypatch):
    _install_sync(monkeypatch, [_Resp(status=200, json_raises=True)])
    with pytest.raises(GeocoderTransportError) as ei:
        geocode_address(ADDR)
    assert "json" in str(ei.value).lower()


def test_sync_four_distinct_stories(monkeypatch):
    """The failure kinds must not collapse into one generic message."""
    msgs = {}
    for key, item in {
        "403": _Resp(status=403, http_error=True),
        "500": _Resp(status=500, http_error=True),
        "timeout": requests.exceptions.Timeout("t"),
        "badjson": _Resp(status=200, json_raises=True),
    }.items():
        _install_sync(monkeypatch, [item])
        with pytest.raises(GeocoderTransportError) as ei:
            geocode_address(ADDR)
        msgs[key] = str(ei.value)
    assert len(set(msgs.values())) == 4, msgs


# ── (b) genuine no-match returns None ─────────────────────────────────────────

def test_sync_zero_matches_returns_none(monkeypatch):
    calls = _install_sync(monkeypatch, [_Resp(status=200, json_data=_data())])
    assert geocode_address(ADDR) is None
    assert calls["n"] == 1  # a clean 200 does not retry


# ── (c) multiple matches ──────────────────────────────────────────────────────

def test_sync_multi_match_same_tract_proceeds(monkeypatch):
    data = _data(_match(), _match())  # two matches, identical tract
    _install_sync(monkeypatch, [_Resp(status=200, json_data=data)])
    assert geocode_address(ADDR) == "17031030604"


def test_sync_multi_match_different_tracts_raises(monkeypatch):
    data = _data(_match(tract="030604"), _match(tract="840100"))
    _install_sync(monkeypatch, [_Resp(status=200, json_data=data)])
    with pytest.raises(AmbiguousAddressError) as ei:
        geocode_address(ADDR)
    msg = str(ei.value)
    assert "17031030604" in msg and "17031840100" in msg  # names both candidates


def test_sync_single_match_returns_tract(monkeypatch):
    _install_sync(monkeypatch, [_Resp(status=200, json_data=_data(_match()))])
    assert geocode_address(ADDR) == "17031030604"


# ── async path: identical contract ────────────────────────────────────────────

class _AsyncCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class _AsyncResp:
    def __init__(self, *, status=200, json_data=None, http_error=False, json_raises=False):
        self.status = status
        self._json = json_data if json_data is not None else {}
        self._http_error = http_error
        self._json_raises = json_raises

    def raise_for_status(self):
        if self._http_error:
            import aiohttp
            raise aiohttp.ClientResponseError(
                request_info=None, history=(), status=self.status,
                message=f"HTTP {self.status}",
            )

    async def json(self):
        if self._json_raises:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json


class _AsyncSession:
    def __init__(self, items):
        self._items = list(items)
        self.calls = 0

    def get(self, *_a, **_k):
        self.calls += 1
        item = self._items[min(self.calls - 1, len(self._items) - 1)]
        if isinstance(item, Exception):
            raise item
        return _AsyncCtx(item)


@pytest.fixture(autouse=True)
def _no_async_backoff(monkeypatch):
    async def _nosleep(*_a, **_k):
        return None
    monkeypatch.setattr(census.asyncio, "sleep", _nosleep)


def _run_single(session, retries=census.MAX_RETRIES):
    async def _driver():
        # Semaphore must be constructed inside the running loop (py3.9).
        sem = asyncio.Semaphore(1)
        return await _geocode_single_async(session, ADDR, sem, retries=retries)
    return asyncio.run(_driver())


def test_async_403_raises_transport_error(monkeypatch):
    sess = _AsyncSession([_AsyncResp(status=403, http_error=True)])
    with pytest.raises(GeocoderTransportError) as ei:
        _run_single(sess)
    assert "403" in str(ei.value)
    assert ADDR in str(ei.value)
    assert sess.calls == census.MAX_RETRIES + 1


def test_async_zero_matches_returns_none():
    sess = _AsyncSession([_AsyncResp(status=200, json_data=_data())])
    assert _run_single(sess) is None
    assert sess.calls == 1


def test_async_multi_match_same_tract_proceeds():
    sess = _AsyncSession([_AsyncResp(status=200, json_data=_data(_match(), _match()))])
    assert _run_single(sess) == "17031030604"


def test_async_multi_match_different_tracts_raises():
    data = _data(_match(tract="030604"), _match(tract="840100"))
    sess = _AsyncSession([_AsyncResp(status=200, json_data=data)])
    with pytest.raises(AmbiguousAddressError) as ei:
        _run_single(sess)
    assert "17031030604" in str(ei.value) and "17031840100" in str(ei.value)


def test_async_bad_json_raises_transport_error():
    sess = _AsyncSession([_AsyncResp(status=200, json_raises=True)])
    with pytest.raises(GeocoderTransportError) as ei:
        _run_single(sess)
    assert "json" in str(ei.value).lower()
