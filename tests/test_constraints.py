"""Binding release constraints C1 and C2 (0.4.0).

C1 — EVERY exception class defined in exceptions.py subclasses NMTCMapperError.
     No exception may escape the package that isn't under that tree. If a new
     leaf were bolted onto ``Exception`` directly, a downstream
     ``except NMTCMapperError`` would miss it and it would surface as an
     un-typed crash — exactly what the typed hierarchy exists to prevent.

C2 — Every indeterminate / "unknown" verdict carries ``nmtc_eligible is None``.
     If such a path returned ``False`` instead, the 1.1.5 flagship adapter would
     render it as a VERIFIED INELIGIBLE — the fabrication this release kills.
"""
import inspect

import pytest

import nmtcmapper.exceptions as exc_mod
from nmtcmapper.exceptions import NMTCMapperError


def _all_exception_classes():
    """Every Exception subclass *defined in* exceptions.py (not imported names)."""
    return [
        obj
        for _name, obj in inspect.getmembers(exc_mod, inspect.isclass)
        if issubclass(obj, BaseException) and obj.__module__ == exc_mod.__name__
    ]


# ── C1 ────────────────────────────────────────────────────────────────────────

def test_c1_every_exception_subclasses_base():
    classes = _all_exception_classes()
    # There must actually be classes to check (guards against an empty sweep
    # silently "passing").
    assert classes, "no exception classes found in exceptions.py"
    for cls in classes:
        if cls is NMTCMapperError:
            continue
        assert issubclass(cls, NMTCMapperError), (
            f"{cls.__name__} does not subclass NMTCMapperError — a downstream "
            f"`except NMTCMapperError` would let it escape the package."
        )


def test_c1_base_is_exception():
    assert issubclass(NMTCMapperError, Exception)


# ── The 0.4.0 new leaves exist and are under the tree ─────────────────────────

def test_new_geocoder_and_schema_exceptions_exist_and_are_typed():
    from nmtcmapper.exceptions import (
        GeocoderError,
        GeocoderTransportError,
        AmbiguousAddressError,
        EligibilitySchemaError,
        EligibilityValueError,
    )
    for cls in (
        GeocoderError,
        GeocoderTransportError,
        AmbiguousAddressError,
        EligibilitySchemaError,
        EligibilityValueError,
    ):
        assert issubclass(cls, NMTCMapperError)
    # geocoder leaves are siblings under GeocoderError
    assert issubclass(GeocoderTransportError, GeocoderError)
    assert issubclass(AmbiguousAddressError, GeocoderError)
    assert not issubclass(GeocoderTransportError, AmbiguousAddressError)


# ── C2 ────────────────────────────────────────────────────────────────────────
# Every indeterminate / "unknown" verdict MUST carry nmtc_eligible is None. If any
# of these carried False, the 1.1.5 adapter would render it as VERIFIED INELIGIBLE.

def test_c2_check_tract_absent_yields_none(sample_table):
    from nmtcmapper.eligibility.checker import check_tract
    r = check_tract("99999999999", sample_table)
    assert r["distress_level"] == "unknown"
    assert r["nmtc_eligible"] is None


def test_c2_check_address_no_match_yields_none(mapper, monkeypatch):
    import nmtcmapper.mapper as mapper_mod
    monkeypatch.setattr(mapper_mod, "geocode_address", lambda a: None)
    res = mapper.check_address("no match anywhere")
    assert res.distress_level == "unknown"
    assert res.nmtc_eligible is None


def test_c2_every_unknown_distress_result_has_none_eligible(sample_table, mapper, monkeypatch):
    """Sweep: assemble every indeterminate path and assert the invariant holds
    for all of them at once — distress 'unknown' <=> nmtc_eligible is None."""
    from nmtcmapper.eligibility.checker import check_tract
    import nmtcmapper.mapper as mapper_mod

    results = []
    # path 1: tract absent from table
    results.append(check_tract("99999999999", sample_table))
    # path 2: geocode no-match
    monkeypatch.setattr(mapper_mod, "geocode_address", lambda a: None)
    r2 = mapper.check_address("no match")
    results.append({"distress_level": r2.distress_level, "nmtc_eligible": r2.nmtc_eligible})
    # path 3: geocode ok but tract absent
    monkeypatch.setattr(mapper_mod, "geocode_address", lambda a: "99999999999")
    r3 = mapper.check_address("valid addr unknown tract")
    results.append({"distress_level": r3.distress_level, "nmtc_eligible": r3.nmtc_eligible})

    for r in results:
        if r["distress_level"] == "unknown":
            assert r["nmtc_eligible"] is None, r
    # and at least all three really were indeterminate (guards a vacuous pass)
    assert all(r["distress_level"] == "unknown" for r in results)
