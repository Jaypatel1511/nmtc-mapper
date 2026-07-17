"""C-1 — the dead async batch path (0.4.0 fix round).

``_batch_geocode_async`` wrapped every coroutine in ``create_task`` inside an
``as_completed`` loop that discarded its results, then ``gather()``-ed the SAME
coroutine objects — re-awaiting an already-driven coroutine raises
``RuntimeError: cannot reuse already awaited coroutine``. Every
``enrich(address_col=)`` / ``geocode_batch(use_async=True)`` call on >=2
addresses died there, yet 95 tests stayed green because none drove the batch
wrapper end to end (they only exercised ``_geocode_single_async``).

These tests drive ``_batch_geocode_async`` (and ``geocode_batch``) themselves:
  1. a multi-address batch returns tracts in order (RED: RuntimeError re-await)
  2. calling from an already-running loop (Jupyter) warns and runs the SYNC
     path — NOT nest_asyncio (an undeclared dependency)
  3. a geocoder error inside a batch propagates as the typed NMTCMapperError
     subclass, not RuntimeError — C1 holds in the batch path too.

All offline: the aiohttp session is faked, backoff sleeps stubbed, and every
test asserts its fake was actually exercised.
"""
import asyncio

import pandas as pd
import pytest

import nmtcmapper.geocoder.census as census
from nmtcmapper.exceptions import GeocoderTransportError, NMTCMapperError

A1 = "111 Alpha St, Chicago, IL 60601"
A2 = "222 Beta Ave, Chicago, IL 60602"


# ── aiohttp fakes (same shapes as tests/test_geocoder_contract.py) ────────────

def _match(state="17", county="031", tract="030604"):
    return {"geographies": {"Census Tracts": [
        {"STATE": state, "COUNTY": county, "TRACT": tract}]}}


def _data(*matches):
    return {"result": {"addressMatches": list(matches)}}


class _AsyncCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class _AsyncResp:
    def __init__(self, *, status=200, json_data=None, http_error=False):
        self.status = status
        self._json = json_data if json_data is not None else {}
        self._http_error = http_error

    def raise_for_status(self):
        if self._http_error:
            import aiohttp
            raise aiohttp.ClientResponseError(
                request_info=None, history=(), status=self.status,
                message=f"HTTP {self.status}",
            )

    async def json(self):
        return self._json


class _FakeSession:
    """Fake aiohttp ClientSession that routes on the parsed street of each
    address, so per-address answers survive concurrent (unordered) execution."""
    def __init__(self, router):
        self._router = router
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, _url, params=None, timeout=None):
        self.calls += 1
        item = self._router(params["street"])
        if isinstance(item, Exception):
            raise item
        return _AsyncCtx(item)


@pytest.fixture(autouse=True)
def _no_async_backoff(monkeypatch):
    async def _nosleep(*_a, **_k):
        return None
    monkeypatch.setattr(census.asyncio, "sleep", _nosleep)


def _install_fake_session(monkeypatch, router):
    session = _FakeSession(router)
    monkeypatch.setattr(census.aiohttp, "TCPConnector", lambda **_k: object())
    monkeypatch.setattr(census.aiohttp, "ClientSession", lambda *_a, **_k: session)
    return session


# ── (1) end-to-end batch: the re-await bug ────────────────────────────────────

def test_batch_geocode_async_returns_ordered_tracts(monkeypatch):
    """RED against current code: RuntimeError 'cannot reuse already awaited
    coroutine' from gather()-ing coroutines already wrapped in create_task."""
    def router(street):
        return _AsyncResp(json_data=_data(
            _match(tract="030604") if street.startswith("111")
            else _match(tract="840100")))

    session = _install_fake_session(monkeypatch, router)

    results = asyncio.run(census._batch_geocode_async([A1, A2]))

    assert results == ["17031030604", "17031840100"]   # order preserved
    assert session.calls == 2                           # fake actually ran, both addrs


# ── (2) already-running loop: warn + sync fallback, never nest_asyncio ────────

def test_geocode_batch_in_running_loop_warns_and_uses_sync(monkeypatch):
    """Inside a live loop (Jupyter), geocode_batch must warn and take the SYNC
    path — not reach for nest_asyncio (absent from Requires-Dist)."""
    calls = {"n": 0}

    def _sync(addr):
        calls["n"] += 1
        return "17031030604" if addr == A1 else "17031840100"

    # If any code reaches for nest_asyncio, make that loudly fail rather than
    # silently succeed off the ambient Anaconda copy.
    import builtins
    real_import = builtins.__import__

    def _no_nest(name, *a, **k):
        if name == "nest_asyncio":
            raise AssertionError("nest_asyncio must not be imported (undeclared dep)")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_nest)
    monkeypatch.setattr(census, "geocode_address", _sync)

    df = pd.DataFrame({"address": [A1, A2]})

    async def _driver():
        return census.geocode_batch(df, use_async=True)

    with pytest.warns(RuntimeWarning):
        out = asyncio.run(_driver())

    assert calls["n"] == 2                                  # sync path taken
    assert list(out["tract_id"]) == ["17031030604", "17031840100"]


# ── (3) geocoder error aborts the batch as a TYPED error, not RuntimeError ────

def test_batch_geocoder_error_propagates_as_typed_error(monkeypatch):
    """A transport failure in one row aborts the whole batch (0.4.0 contract),
    surfacing as GeocoderTransportError — a NMTCMapperError, never RuntimeError."""
    def router(street):
        if street.startswith("111"):
            return _AsyncResp(status=403, http_error=True)   # -> GeocoderTransportError
        return _AsyncResp(json_data=_data(_match(tract="840100")))

    session = _install_fake_session(monkeypatch, router)

    with pytest.raises(GeocoderTransportError) as ei:
        asyncio.run(census._batch_geocode_async([A1, A2]))

    assert isinstance(ei.value, NMTCMapperError)      # C1 holds here
    assert not isinstance(ei.value, RuntimeError)     # not the re-await crash
    assert session.calls >= 1                         # fake actually ran
