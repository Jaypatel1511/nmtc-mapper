"""F4 — explicit sample mode.

Sample data survives only as a deliberate, provenance-marked opt-in. It must
NEVER be reachable implicitly from a failure path (that's F2/F3), and when used
explicitly it must (a) require no network, and (b) stamp the mapper so downstream
code can tell a demo answer from a real one.
"""
import pytest
from nmtcmapper.mapper import NMTCMapper


def test_load_sample_table_public():
    from nmtcmapper import load_sample_table
    df = load_sample_table()
    assert len(df) == 12
    assert df["nmtc_eligible"].any()


def test_underscore_alias_preserved_for_notebook():
    # examples/ notebook imports the private name — keep it working.
    from nmtcmapper.data.loader import _build_sample_table, load_sample_table
    assert len(_build_sample_table()) == 12
    assert _build_sample_table is load_sample_table


def test_from_sample_explicit_works(monkeypatch):
    # The whole contract: zero network. Any requests.get is a hard failure.
    def _no_network(*a, **k):
        raise AssertionError("from_sample() must not touch the network")
    monkeypatch.setattr("nmtcmapper.data.loader.requests.get", _no_network)

    m = NMTCMapper.from_sample()
    assert m.tract_count == 12
    assert m.oz_tract_count == 6
    assert m.data_source == "sample"
    # sample data still answers the known eligible demo tract
    assert m.check_tract("17031840100").nmtc_eligible is True


def test_data_source_marker(monkeypatch):
    """Real-path constructor stamps data_source == 'cdfi_fund' (mocked success)."""
    from nmtcmapper import load_sample_table
    fake_table = load_sample_table()  # any real-shaped frame stands in for the CDFI download
    monkeypatch.setattr(
        "nmtcmapper.mapper.load_eligibility_table", lambda force=False: fake_table
    )
    monkeypatch.setattr(
        "nmtcmapper.mapper.load_opportunity_zones", lambda force=False: {"17031840100"}
    )
    m = NMTCMapper()
    assert m.data_source == "cdfi_fund"


def test_data_source_surfaced_in_repr():
    m = NMTCMapper.from_sample()
    assert "sample" in repr(m).lower()
