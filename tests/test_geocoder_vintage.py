"""0.4.1 — geocoder vintage aligned to the eligibility table's tract basis.

THE BUG (0.4.0): the geocoder sent ``vintage=Current_Current``, which tracks the
newest TIGER release, while the CDFI Fund eligibility table is frozen on 2020
census tracts. Connecticut's 2022 ACS county switch (8 legacy counties ->
9 COG/planning regions) made the county FIPS — the middle 5 digits of every
tract GEOID — diverge, so the join stopped matching and 883 CT tracts
(316 eligible) returned not-found.

THE FIX: ``vintage=Census2020_Current`` — current address ranges (new
construction still geocodes) resolved onto 2020 tract geography (what the table
carries). Bound structurally in ``schema.TRACT_VINTAGE`` so the table basis and
the geocoder vintage cannot be edited apart (see ``test_binding_*`` below).

All tests here are offline: ``requests.get`` / the aiohttp session are mocked
with a fake that MODELS the live Census vintage matrix (re-verified 2026-07-17),
and every network-mocking test asserts its mock was actually exercised.
"""
import asyncio

import pandas as pd
import pytest

import nmtcmapper.data.schema as schema
import nmtcmapper.geocoder.census as census
from nmtcmapper.data.schema import TractVintage, TRACT_VINTAGE
from nmtcmapper.geocoder.census import _geocoder_params, _geocode_single_async
from nmtcmapper.mapper import NMTCMapper


# ── live-verified vintage matrix (2026-07-17) ─────────────────────────────────
# (street, vintage) -> 11-digit tract the live Census geocoder returns.
#   Hartford 765 Asylum Ave: Current_Current -> COG tract 09110... (bug);
#            Census2020_Current -> legacy-county tract 09003... (fix).
#   Seattle 400 Broad St: 2020 geography -> ...007101; 2010 geography -> ...007100
#            (the tract split 2010->2020) — proves a Census2010 "fix" is wrong.
#   Chicago 5701 N Sheridan Rd: unchanged across vintages — non-CT control.
_VINTAGE_MATRIX = {
    ("765 Asylum Ave",     "Current_Current"):    "09110524600",
    ("765 Asylum Ave",     "Census2020_Current"): "09003524600",
    ("765 Asylum Ave",     "Census2010_Current"): "09003524600",
    ("400 Broad St",       "Current_Current"):    "53033007101",
    ("400 Broad St",       "Census2020_Current"): "53033007101",
    ("400 Broad St",       "Census2010_Current"): "53033007100",
    ("5701 N Sheridan Rd", "Current_Current"):    "17031030604",
    ("5701 N Sheridan Rd", "Census2020_Current"): "17031030604",
    ("5701 N Sheridan Rd", "Census2010_Current"): "17031030604",
}

HARTFORD = "765 Asylum Ave, Hartford, CT 06105"
SEATTLE  = "400 Broad St, Seattle, WA 98109"
CHICAGO  = "5701 N Sheridan Rd, Chicago, IL 60660"


def _matches_for(tract: str) -> dict:
    return {"result": {"addressMatches": [
        {"geographies": {"Census Tracts": [
            {"STATE": tract[:2], "COUNTY": tract[2:5], "TRACT": tract[5:]}]}}
    ]}}


class _Resp:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


def _install_matrix_get(monkeypatch):
    """Mock census.requests.get with a fake that resolves (street, vintage)
    through the live-verified matrix. Returns a call counter so every test can
    assert its mock ran and can read back the vintage that was actually sent."""
    calls = {"n": 0, "vintages": []}

    def _get(url, params=None, timeout=None):
        calls["n"] += 1
        street = params["street"]
        vintage = params["vintage"]
        calls["vintages"].append(vintage)
        tract = _VINTAGE_MATRIX.get((street, vintage))
        if tract is None:
            return _Resp({"result": {"addressMatches": []}})  # no-match
        return _Resp(_matches_for(tract))

    monkeypatch.setattr(census.requests, "get", _get)
    return calls


def _table(*eligible_tracts: str) -> pd.DataFrame:
    """A minimal eligibility table (loader-shaped columns) containing exactly the
    given tracts, all flagged eligible. Any tract NOT listed is absent -> the
    check returns the indeterminate not-found verdict."""
    recs = []
    for tid in eligible_tracts:
        recs.append({
            "tract_id": tid, "nmtc_eligible": True, "distress_level": "lic",
            "poverty_rate": 0.25, "ami_ratio": 0.70, "unemployment_rate": 0.08,
            "is_non_metro": False, "is_high_migration_rural": False,
            "severe_distress": False,
            "deep_distress": False,
        })
    return pd.DataFrame(recs).set_index("tract_id")


def _mapper_with(*eligible_tracts: str) -> NMTCMapper:
    m = NMTCMapper.__new__(NMTCMapper)
    m._table = _table(*eligible_tracts)
    m._oz_tracts = set()
    m.data_source = "test"
    return m


# ── param-level: the vintage sent is the 2020-tract vintage ────────────────────

def test_sync_geocoder_sends_census2020_vintage():
    params = _geocoder_params(HARTFORD)
    assert params["vintage"] == "Census2020_Current"
    # benchmark stays CURRENT so new construction still geocodes.
    assert params["benchmark"] == "Public_AR_Current"


def test_async_and_sync_geocoder_share_the_same_vintage():
    # Both paths build params through the ONE helper; if a future edit forks
    # them, this catches the split (it has happened in this package before).
    assert _geocoder_params(SEATTLE)["vintage"] == "Census2020_Current"
    assert _geocoder_params(CHICAGO)["vintage"] == "Census2020_Current"


# ── behavioral: Hartford is the negative case (RED on 0.4.0) ───────────────────

def test_hartford_resolves_to_legacy_county_tract_and_gets_real_verdict(monkeypatch):
    calls = _install_matrix_get(monkeypatch)
    mapper = _mapper_with("09003524600")  # legacy-county tract IS in the table
    result = mapper.check_address(HARTFORD)

    assert calls["n"] > 0                                   # mock actually ran
    assert calls["vintages"] == ["Census2020_Current"]      # ...with the fix vintage
    assert result.tract_id == "09003524600"                 # NOT the COG 09110524600
    assert result.eligibility_status == "verified-eligible" # a real verdict, not not-found
    assert result.nmtc_eligible is True                     # never None/unknown


def test_hartford_cog_tract_is_absent_from_table():
    # Guards the diagnosis: the COG GEOID that Current_Current returns is not a
    # table key, so on 0.4.0 Hartford fell to not-found.
    mapper = _mapper_with("09003524600")
    assert "09110524600" not in mapper._table.index


# ── behavioral: Seattle proves the fix is NOT Census2010 ───────────────────────

def test_seattle_resolves_to_2020_tract_not_the_2010_tract(monkeypatch):
    calls = _install_matrix_get(monkeypatch)
    # Table carries the 2020 tract; a Census2010 "fix" would return ...007100,
    # which is absent -> not-found. Under the correct 2020 vintage it verifies.
    mapper = _mapper_with("53033007101")
    result = mapper.check_address(SEATTLE)

    assert calls["n"] > 0
    assert result.tract_id == "53033007101"                 # the 2020 tract
    assert result.tract_id != "53033007100"                 # NOT the 2010 tract
    assert result.eligibility_status == "verified-eligible"


# ── behavioral: non-CT control unchanged ───────────────────────────────────────

def test_chicago_control_unchanged(monkeypatch):
    calls = _install_matrix_get(monkeypatch)
    mapper = _mapper_with("17031030604")
    result = mapper.check_address(CHICAGO)

    assert calls["n"] > 0
    assert result.tract_id == "17031030604"
    assert result.eligibility_status == "verified-eligible"


# ── async parity: the async path carries the SAME vintage ──────────────────────

class _AsyncCtx:
    def __init__(self, resp): self._resp = resp
    async def __aenter__(self): return self._resp
    async def __aexit__(self, *a): return False


class _AsyncResp:
    def __init__(self, json_data): self._json = json_data
    def raise_for_status(self): return None
    async def json(self): return self._json


class _AsyncSession:
    """Records the vintage the async path actually sends, and resolves it through
    the same live-verified matrix as the sync fake."""
    def __init__(self): self.vintages = []
    def get(self, url, params=None, timeout=None):
        self.vintages.append(params["vintage"])
        tract = _VINTAGE_MATRIX.get((params["street"], params["vintage"]))
        body = _matches_for(tract) if tract else {"result": {"addressMatches": []}}
        return _AsyncCtx(_AsyncResp(body))


def test_async_path_sends_census2020_and_resolves_hartford_legacy_tract(monkeypatch):
    async def _nosleep(*_a, **_k): return None
    monkeypatch.setattr(census.asyncio, "sleep", _nosleep)

    sess = _AsyncSession()

    async def _driver():
        sem = asyncio.Semaphore(1)
        return await _geocode_single_async(sess, HARTFORD, sem)

    tract = asyncio.run(_driver())
    assert sess.vintages == ["Census2020_Current"]   # async carries the fix vintage
    assert tract == "09003524600"                     # ...and the legacy-county tract


# ── the structural binding has teeth: vintage & table basis cannot desync ──────

def test_binding_refuses_to_construct_when_vintage_drifts_from_basis():
    # Bump the table basis to 2025 but forget the geocoder vintage: the exact
    # edit that reintroduces the CT-class bug. It must not be constructible.
    with pytest.raises(ValueError):
        TractVintage(
            basis_year=2025,
            geocoder_benchmark="Public_AR_Current",
            geocoder_vintage="Census2020_Current",   # stale — drifted from 2025
            table_geoid_header="2025 Census Tract Number FIPS code. GEOID",
        )
    # Move the vintage but forget the table header: also refused.
    with pytest.raises(ValueError):
        TractVintage(
            basis_year=2020,
            geocoder_benchmark="Public_AR_Current",
            geocoder_vintage="Census2010_Current",   # drifted the other way
            table_geoid_header="2020 Census Tract Number FIPS code. GEOID",
        )


def test_binding_accepts_a_consistent_future_vintage():
    # A future ACS table on 2025 tracts is fine — SO LONG AS both move together.
    v = TractVintage(
        basis_year=2025,
        geocoder_benchmark="Public_AR_Current",
        geocoder_vintage="Census2025_Current",
        table_geoid_header="2025 Census Tract Number FIPS code. GEOID",
    )
    assert v.geocoder_vintage == "Census2025_Current"


def test_loader_header_and_geocoder_vintage_read_the_one_binding():
    # Both consumers agree with the binding. (The teeth that make desync
    # IMPOSSIBLE are the __post_init__ guard above and the loader-rejection test
    # below — this just documents that the loader header and geocoder params are
    # sourced from TRACT_VINTAGE, not from independent literals.)
    assert schema.ELIGIBILITY_XLSB_EXPECTED_HEADERS[0] == TRACT_VINTAGE.table_geoid_header
    params = _geocoder_params(HARTFORD)
    assert params["vintage"] == TRACT_VINTAGE.geocoder_vintage
    assert params["benchmark"] == TRACT_VINTAGE.geocoder_benchmark
    # Both the table header and the geocoder vintage name the SAME basis year,
    # so one edit point governs both.
    assert str(TRACT_VINTAGE.basis_year) in schema.ELIGIBILITY_XLSB_EXPECTED_HEADERS[0]
    assert f"Census{TRACT_VINTAGE.basis_year}" in params["vintage"]


def _header_row(overrides: dict = None) -> list:
    """A full 16-column .xlsb header row matching the expected layout, with
    optional {index: header} overrides."""
    row = ["" for _ in range(schema.ELIGIBILITY_XLSB_COLUMN_COUNT)]
    for i, h in schema.ELIGIBILITY_XLSB_EXPECTED_HEADERS.items():
        row[i] = h
    for i, h in (overrides or {}).items():
        row[i] = h
    return row


def test_loader_rejects_a_table_whose_tract_basis_disagrees_with_the_binding():
    # The loader enforces the binding's tract basis on the DOWNLOADED file: a
    # table declaring a different census-tract vintage in column 0 is refused
    # before any row is trusted. This is the loader half of the binding — if the
    # geocoder ever moved vintage, the table on the OLD basis would no longer
    # validate, so the two cannot silently run on different geographies.
    from nmtcmapper.data.loader import _validate_xlsb_header
    from nmtcmapper.exceptions import EligibilitySchemaError

    bad = _header_row({0: "2010 Census Tract Number FIPS code. GEOID"})
    with pytest.raises(EligibilitySchemaError):
        _validate_xlsb_header(bad)

    _validate_xlsb_header(_header_row())  # the binding's own basis validates cleanly


def test_live_binding_is_the_2020_census2020_pairing():
    assert TRACT_VINTAGE.basis_year == 2020
    assert TRACT_VINTAGE.geocoder_vintage == "Census2020_Current"
    assert TRACT_VINTAGE.geocoder_benchmark == "Public_AR_Current"
