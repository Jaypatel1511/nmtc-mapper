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


def _forbid_real_data_access(monkeypatch, tmp_path):
    """Make the TRANSPORT raise, so "mocked" means mocked — not "mostly mocked".

    RULE: when a constructor gains a dependency, every test that mocks that
    constructor's dependencies silently rots. The mock list is an undeclared
    contract between the constructor and its tests, and nothing checks that it
    is complete. A test that mocks 2 of 3 loaders does not fail — it quietly
    starts doing real I/O, invisibly on a networked machine.

    So this asserts the ABSENCE of the behaviour (no network call at all)
    rather than the presence of the mocks. A future FOURTH loader added to
    NMTCMapper.__init__ reddens this test the moment it is added, instead of
    the moment someone runs the suite offline.

    The cache redirect is what gives the tripwire teeth. Without it the gate is
    machine-dependent theatre: on a developer box with a warm ~/.nmtcmapper
    cache an unmocked loader is satisfied from DISK, never touches the
    transport, and the tripwire stays silent — which is exactly how the
    unmocked load_oz2_table() survived the 0.6.0 build session's green run.
    Pointing the cache at an empty directory forces any unmocked loader to
    reach for the network, where the tripwire is waiting.
    """
    monkeypatch.setattr("nmtcmapper.data.loader.CACHE_DIR", str(tmp_path / "cold"))

    def _boom(*a, **k):
        raise AssertionError(
            "mocked NMTCMapper() construction performed a real network call — a "
            "constructor dependency is missing from this test's mock list"
        )
    monkeypatch.setattr("requests.Session.request", _boom)
    monkeypatch.setattr("requests.get", _boom)
    monkeypatch.setattr("nmtcmapper.data.loader.requests.get", _boom)


def test_data_source_marker(monkeypatch, tmp_path):
    """Real-path constructor stamps data_source == 'cdfi_fund' (mocked success).

    EVERY loader NMTCMapper.__init__ calls is mocked here, and the tripwire
    above proves it: 0.6.0 added load_oz2_table() as a third call and this test
    went on "passing" by downloading Treasury's file for real.
    """
    from nmtcmapper import load_sample_table
    from nmtcmapper.data.loader import _sample_oz2_table
    fake_table = load_sample_table()  # any real-shaped frame stands in for the CDFI download
    monkeypatch.setattr(
        "nmtcmapper.mapper.load_eligibility_table", lambda force=False: fake_table
    )
    monkeypatch.setattr(
        "nmtcmapper.mapper.load_opportunity_zones", lambda force=False: {"17031840100"}
    )
    # The third loader — added by 0.6.0 at mapper.py:106 and never mocked here.
    monkeypatch.setattr(
        "nmtcmapper.mapper.load_oz2_table", lambda force=False: _sample_oz2_table()
    )
    _forbid_real_data_access(monkeypatch, tmp_path)

    m = NMTCMapper()
    assert m.data_source == "cdfi_fund"


def test_data_source_surfaced_in_repr():
    m = NMTCMapper.from_sample()
    assert "sample" in repr(m).lower()
