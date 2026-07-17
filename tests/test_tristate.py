"""Fixes 2 & 3 — tri-state eligibility (0.4.0).

nmtc_eligible becomes Optional[bool]:
  True  -> verified eligible
  False -> verified ineligible (the table explicitly says NO)
  None  -> INDETERMINATE — geocode no-match, or a tract absent from the ~85k
           universe (a bad/unknown tract id or a vintage mismatch, NOT a
           verified "ineligible").

An indeterminate verdict must NEVER surface as False/"ineligible": the 1.1.5
adapter would render False as a VERIFIED INELIGIBLE (fabrication). Constraint C2.
"""
import pandas as pd
import pytest

from nmtcmapper.eligibility.checker import check_tract, EligibilityResult
from nmtcmapper.exceptions import GeocoderTransportError, AmbiguousAddressError
import nmtcmapper.mapper as mapper_mod


# ── Fix 3: check_tract lookup miss ────────────────────────────────────────────

def test_check_tract_absent_is_indeterminate(sample_table):
    """A syntactically-valid but absent tract is NOT ineligible — it is unknown."""
    r = check_tract("99999999999", sample_table)
    assert r["nmtc_eligible"] is None            # C2 — not False
    assert r["distress_level"] == "unknown"      # not "ineligible"
    assert r["poverty_rate"] is None
    assert r["ami_ratio"] is None
    assert r["unemployment_rate"] is None
    assert r["tract_found"] is False             # explicit field, not "notice metrics are None"


def test_check_tract_present_ineligible_is_verified_false(sample_table):
    """A tract the table explicitly rules out stays a hard, verified False."""
    r = check_tract("17031010100", sample_table)   # in the 12-tract sample, ineligible
    assert r["nmtc_eligible"] is False
    assert r["distress_level"] == "ineligible"
    assert r["tract_found"] is True


def test_check_tract_present_eligible_is_verified_true(sample_table):
    r = check_tract("17031840100", sample_table)
    assert r["nmtc_eligible"] is True
    assert r["tract_found"] is True


def test_absent_and_ineligible_are_distinguishable(sample_table):
    absent = check_tract("99999999999", sample_table)
    ineligible = check_tract("17031010100", sample_table)
    # The whole point of Fix 3: a caller can tell them apart on an explicit field.
    assert absent["tract_found"] is False
    assert ineligible["tract_found"] is True
    assert absent["nmtc_eligible"] is None
    assert ineligible["nmtc_eligible"] is False


# ── Fix 2: check_address ──────────────────────────────────────────────────────

def test_check_address_no_match_is_indeterminate(mapper, monkeypatch):
    """geocode genuine no-match (None) -> unknown, never False/ineligible."""
    called = {"n": 0}

    def _no_match(addr):
        called["n"] += 1
        return None

    monkeypatch.setattr(mapper_mod, "geocode_address", _no_match)
    res = mapper.check_address("Nowhere Real, XX 00000")
    assert called["n"] == 1                       # mock actually exercised
    assert res.nmtc_eligible is None              # C2
    assert res.distress_level == "unknown"
    assert res.geocode_success is False
    assert res.poverty_rate is None
    assert res.ami_ratio is None


def test_check_address_transport_error_propagates(mapper, monkeypatch):
    """A typed geocoder transport error is NOT swallowed into a fake result."""
    def _boom(addr):
        raise GeocoderTransportError("HTTP 403 Forbidden for %r" % addr)

    monkeypatch.setattr(mapper_mod, "geocode_address", _boom)
    with pytest.raises(GeocoderTransportError):
        mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")


def test_check_address_ambiguous_error_propagates(mapper, monkeypatch):
    def _amb(addr):
        raise AmbiguousAddressError("two tracts")

    monkeypatch.setattr(mapper_mod, "geocode_address", _amb)
    with pytest.raises(AmbiguousAddressError):
        mapper.check_address("somewhere")


def test_check_address_geocoded_but_tract_absent_is_indeterminate(mapper, monkeypatch):
    """Geocode SUCCEEDS but the tract is not in the table -> unknown, and
    geocode_success stays True (the geocode was fine; the lookup missed)."""
    monkeypatch.setattr(mapper_mod, "geocode_address", lambda a: "99999999999")
    res = mapper.check_address("valid addr but unknown tract")
    assert res.geocode_success is True
    assert res.tract_found is False
    assert res.nmtc_eligible is None
    assert res.distress_level == "unknown"


def test_check_address_geocoded_eligible_tract(mapper, monkeypatch):
    monkeypatch.setattr(mapper_mod, "geocode_address", lambda a: "17031840100")
    res = mapper.check_address("real eligible addr")
    assert res.geocode_success is True
    assert res.tract_found is True
    assert res.nmtc_eligible is True
