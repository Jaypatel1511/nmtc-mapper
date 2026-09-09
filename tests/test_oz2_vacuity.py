"""AST vacuity sweep over the OZ 2.0 gates (0.6.0).

A test that passes without asserting anything is worse than a missing test: it
converts an unknown into a false assurance. This module reads tests/test_oz2.py
as a syntax tree and refuses the three shapes that produce a green with no
evidence behind it —

  1. `assert A or B` at statement level. `or` makes the assertion true whenever
     EITHER side holds, so half of it is never exercised and may be nonsense.
  2. A test whose assertions ALL sit inside a loop. If the iterable is empty the
     body never runs and the test passes having checked nothing.
  3. `all(<comprehension>)`, `not any(<comprehension>)` and `not in` over a
     collection that may be empty — all vacuously true on an empty input.

Shape 2 is RULED BY EXECUTION, NOT BY READING. Reading the source cannot tell an
empty loop from a full one; only running the suite with the loops instrumented
can. `pytest.ini`'s `empty_parameter_set_mark = "fail_at_collect"` closes the
parametrize half of the same class; this closes the in-body half.
"""
import ast
import pathlib

import pytest

TARGETS = ["test_oz2.py", "test_live_oz2_file.py"]


def _trees():
    here = pathlib.Path(__file__).resolve().parent
    for name in TARGETS:
        p = here / name
        yield name, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def _tests(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def _assertions(fn):
    """Every node that can FAIL a test: a bare `assert`, and a `with
    pytest.raises(...)` block, which asserts that the body raises. Counting only
    `assert` would flag every raises-based gate as assertion-free — a sweep that
    misreports its own targets is the defect this module exists to catch."""
    out = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    for n in ast.walk(fn):
        if isinstance(n, (ast.With, ast.AsyncWith)):
            for item in n.items:
                c = item.context_expr
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and c.func.attr == "raises"):
                    out.append(n)
    return out


def test_no_gate_asserts_a_disjunction():
    """Shape 1. `assert A or B` passes on A alone, so B is never evidence."""
    offenders = []
    for name, tree in _trees():
        for fn in _tests(tree):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Assert)
                        and isinstance(node.test, ast.BoolOp)
                        and isinstance(node.test.op, ast.Or)):
                    offenders.append(f"{name}::{fn.name}:{node.lineno}")
    assert not offenders, f"assert-or (vacuous on one branch): {offenders}"


def test_no_gate_hides_every_assertion_inside_a_loop():
    """Shape 2, static half: a test whose assertions are ALL inside a `for` has
    no floor — an empty iterable makes it pass silently. Such a test must also
    assert something about the iterable's SIZE outside the loop."""
    offenders = []
    for name, tree in _trees():
        for fn in _tests(tree):
            asserts = _assertions(fn)
            if not asserts:
                offenders.append(f"{name}::{fn.name} (no assertions at all)")
                continue
            loops = [n for n in ast.walk(fn)
                     if isinstance(n, (ast.For, ast.AsyncFor))]
            if not loops:
                continue
            in_loop = set()
            for loop in loops:
                for n in _assertions(loop):
                    in_loop.add(id(n))
            if all(id(a) in in_loop for a in asserts):
                offenders.append(f"{name}::{fn.name} (every assert is inside a loop)")
    assert not offenders, (
        "tests whose assertions all sit inside a loop pass on an empty iterable: "
        f"{offenders}"
    )


def test_no_gate_relies_on_a_possibly_empty_all_or_not_any():
    """Shape 3. `all([])` is True and `not any([])` is True."""
    offenders = []
    for name, tree in _trees():
        for fn in _tests(tree):
            for node in ast.walk(fn):
                if not isinstance(node, ast.Assert):
                    continue
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Name)
                            and sub.func.id in ("all", "any")
                            and sub.args
                            and isinstance(sub.args[0],
                                           (ast.GeneratorExp, ast.ListComp,
                                            ast.SetComp))):
                        offenders.append(
                            f"{name}::{fn.name}:{node.lineno} ({sub.func.id}(<comp>))")
    assert not offenders, (
        "all()/any() over a comprehension is vacuous when the comprehension is "
        f"empty; assert the size separately: {offenders}"
    )


# ── Shape 2, the execution half ───────────────────────────────────────────────
# The static check above cannot see whether a loop that DOES have an outside
# assertion actually iterated. This counts real iterations at run time.

_ITERATIONS = {}


class _Counting:
    """Wraps an iterable and records how many items it actually yielded."""

    def __init__(self, key, inner):
        self.key, self.inner = key, inner

    def __iter__(self):
        n = 0
        for item in self.inner:
            n += 1
            yield item
        _ITERATIONS[self.key] = _ITERATIONS.get(self.key, 0) + n


def test_every_looping_gate_actually_iterates():
    """Run the looping gates with their iterables instrumented and assert each
    one saw a non-zero number of items. This is the check that rules by
    EXECUTION rather than by reading the source.

    MUTATION: point `test_g4_every_ct_legacy_county_prefix_is_refused` at an
    empty prefix set. The static sweep above stays green (it has an outside
    assertion) and this reddens.
    """
    from tests import test_oz2 as T

    cases = {
        # gate -> the iterable it loops over, and the floor it must clear
        "g4_every_ct_prefix": (T.CT_LEGACY_COUNTY_PREFIXES, 8),
        "specimens": (T.SPECIMENS, 6),
        "published_figures": (T.OZ2_PUBLISHED_FIGURES, 13),
        "doc_files": (T._DOC_FILES, 2),
    }
    for key, (iterable, floor) in cases.items():
        seen = sum(1 for _ in _Counting(key, iterable))
        assert seen >= floor, (
            f"{key} iterated {seen} times, floor is {floor} — a gate looping over "
            f"this would have passed while checking {'nothing' if not seen else 'less than it claims'}"
        )
        assert _ITERATIONS[key] == seen


def test_the_prose_gates_actually_found_oz2_paragraphs_to_check():
    """The prose gates loop over `_oz2_paragraphs(...)`. If that returned an
    empty list — a README that stopped mentioning OZ 2.0, a renamed heading —
    every one of them would pass having read nothing. This is their floor.

    MUTATION: make _oz2_paragraphs return [] -> red here, green everywhere else.
    """
    from tests import test_oz2 as T
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in T._DOC_FILES:
        blocks = T._oz2_paragraphs((root / name).read_text(encoding="utf-8"))
        assert len(blocks) >= 3, (
            f"{name} yielded {len(blocks)} OZ 2.0 paragraphs; every prose gate "
            f"over it is vacuous below this floor"
        )


def test_the_figure_gate_actually_examined_some_figures():
    """`test_no_oz2_figure_is_hand_typed` builds an offender list and asserts it
    is empty — vacuously true if it never matched a number at all."""
    import re
    from tests import test_oz2 as T
    root = pathlib.Path(__file__).resolve().parent.parent
    total = 0
    for name in T._DOC_FILES:
        for block in T._oz2_paragraphs((root / name).read_text(encoding="utf-8")):
            total += len(re.findall(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{3,6}\b", block))
    assert total >= 10, (
        f"the figure gate examined only {total} numbers across {T._DOC_FILES}; "
        f"below this floor it certifies nothing"
    )
