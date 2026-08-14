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


# ── C1b (0.5.0): the SHAPE of the tree, not just its root ────────────────────
#
# docs-check.toml's own limitations section says the gate cannot verify this:
# "assertion 6 checks that each exception NAME appears in the README. It does not
# check the inheritance relationships the README draws ... a rewiring of the
# hierarchy stays green." 0.5.0 puts the whole tree in the README, so the shape
# needs a test rather than a documented blind spot. This is the closure the
# methodology (§M8.2) asked the build to add.

# The exact parent of every class, mirroring the ASCII tree in exceptions.py's
# module docstring and in README "Exception hierarchy". Adding a leaf without
# adding it here fails test_c1b_every_exception_class_is_in_this_map.
EXPECTED_PARENTS = {
    "NMTCMapperError":          Exception,
    "EligibilityDataError":     "NMTCMapperError",
    "EligibilityDownloadError": "EligibilityDataError",
    "EligibilityParseError":    "EligibilityDataError",
    "EligibilitySchemaError":   "EligibilityDataError",
    "EligibilityValueError":    "EligibilityDataError",
    "OZDataError":              "NMTCMapperError",
    "OZDownloadError":          "OZDataError",
    "OZParseError":             "OZDataError",
    "GeocoderError":            "NMTCMapperError",
    "GeocoderTransportError":   "GeocoderError",
    "AmbiguousAddressError":    "GeocoderError",
}


def test_c1b_every_exception_class_is_in_this_map():
    """A leaf added to exceptions.py without a row here is an undocumented
    rewiring — the empty-sweep failure mode, closed in both directions."""
    found = {c.__name__ for c in _all_exception_classes()}
    assert found == set(EXPECTED_PARENTS), (
        f"exceptions.py and EXPECTED_PARENTS disagree: "
        f"only in module {sorted(found - set(EXPECTED_PARENTS))}, "
        f"only in map {sorted(set(EXPECTED_PARENTS) - found)}"
    )


def test_c1b_direct_parent_of_every_exception_class():
    """DIRECT parent, via __bases__ — not `issubclass`. `issubclass` passes for
    any ancestor, so it cannot tell the README's three-level tree from a flat
    one where every leaf hangs off NMTCMapperError."""
    for name, expected in EXPECTED_PARENTS.items():
        cls = getattr(exc_mod, name)
        bases = cls.__bases__
        assert len(bases) == 1, f"{name} has multiple bases: {bases}"
        want = expected if isinstance(expected, type) else getattr(exc_mod, expected)
        assert bases[0] is want, (
            f"{name}'s direct parent is {bases[0].__name__}, "
            f"README and exceptions.py draw {want.__name__}"
        )


def test_c1b_the_readme_and_the_docstring_draw_the_same_tree():
    """The README's tree was copied from exceptions.py's module docstring so one
    diagram documents all twelve. Copies drift; this pins them together on the
    parent-child edges rather than on whitespace."""
    from pathlib import Path
    readme = Path(__file__).resolve().parent.parent / "README.md"
    # NOT a skip. Every context that runs this suite ships README.md beside
    # tests/: the checkout, the sdist (MANIFEST.in `include README.md` plus
    # `recursive-include tests *.py` — both verified present in the 0.5.0
    # tarball); the docs-check harness, which copies both; and release.yml's
    # test-wheel job, which copies it beside pyproject.toml. That fourth
    # context was NOT true when this assertion was written: the enumeration
    # was verified against the tarball and asserted of every context, and
    # v0.5.0's first Release run failed on all four interpreters because of
    # it. The workflow was corrected; the assertion was not softened. A skip here would
    # be a test that certifies nothing while reporting green, which is the same
    # vacuity class `empty_parameter_set_mark = "fail_at_collect"` closes in
    # pyproject.toml.
    assert readme.exists(), (
        f"README.md not found at {readme} — the suite must run beside the README "
        f"it asserts against; a missing README is a packaging defect, not a "
        f"reason to pass."
    )
    text = readme.read_text(encoding="utf-8")
    for name in EXPECTED_PARENTS:
        assert name in text, f"{name} missing from README"
    # Locate the drawn tree: the line where each class is the FIRST identifier on
    # the line, after stripping indentation and box-drawing glyphs. That is what
    # a tree row looks like and what a prose mention does not.
    row_of = {}
    for i, raw in enumerate(text.splitlines()):
        head = raw.strip().lstrip("├└─│ ").split(" ")[0].split("\t")[0]
        if head in EXPECTED_PARENTS and head not in row_of:
            row_of[head] = i
    for name in EXPECTED_PARENTS:
        assert name in row_of, f"{name} is not drawn as a row in the README tree"
    # every leaf must be drawn UNDER its parent: the parent's row comes first
    for name, expected in EXPECTED_PARENTS.items():
        if isinstance(expected, type):
            continue
        assert row_of[expected] < row_of[name], (
            f"README draws {name} before its parent {expected}"
        )
