"""FIX2 (0.6.0) — the `eligibility_status` vocabulary is stated ONCE.

RULE: a public enumeration stated in prose is a contract with no compiler.
Every place it is written is a copy, and copies drift silently. 7d18d7f added
a fifth value and updated five of the seven statement sites; the two it missed
were the count word above the README's opening list ("four outcomes" over a
five-item list) and — worse — the biconditional that tells a reader how to find
indeterminate rows:

    The four Optional[bool] columns are None EXACTLY when eligibility_status
    is `not-found` or `geocode-failed`.

A territory row has all four booleans None and neither status, so the filter
that sentence licenses silently drops every territory row and the README then
reads their absence as a supportable NO. The suite was green throughout,
because nothing bound the statement sites to the enumeration. This module is
that binding.

Three things are gated, in order of what they prove:

  1. `ELIGIBILITY_STATUS_VALUES` in schema.py is LOAD-BEARING, not decorative:
     the set of statuses the two producers actually emit — the property and
     `enrich_dataframe`, driven across all five paths — equals the constant
     exactly. Two-sided: a value the code emits but the constant omits reddens,
     and so does a value the constant lists but the code never produces.
  2. Every statement site names every value, with hard-wrapping normalized
     first — the README wraps its opening list across three lines — and any
     count word beside the enumeration ("four outcomes", "Five-way") agrees
     with `len(ELIGIBILITY_STATUS_VALUES)`.
  3. Every "None exactly when / no row was read" sentence names every
     INDETERMINATE status, where "indeterminate" is derived from execution
     (the statuses whose row carried nmtc_eligible None), not typed here.

(j4): a gate whose search returns zero matches must FAIL, not pass. Each site
is asserted located and non-empty, and each locator is asserted to have found
something, before anything is asserted about content. The site list itself is
floored in tests/test_oz2_vacuity.py beside the other looping gates.

MUTATIONS (all observed red before this shipped, each at exactly one test):
  - delete `not-covered-territory` from README.md's opening list -> red at
    test_the_enumeration_is_stated_in_full_somewhere_in_each_site[README.md]
    (the README still names the value in its column table, so the
    every-value gate stays green; the partial-list gate is what catches a
    four-of-five copy)
  - change README.md:14 "five outcomes" back to "four outcomes" -> red at
    test_no_count_word_beside_the_enumeration_disagrees_with_it[README.md]
  - drop `not-covered-territory` from the README's "None exactly when"
    sentence -> red at
    test_every_none_exactly_when_sentence_names_every_indeterminate_status[README.md]
  - remove `not-covered-territory` from ELIGIBILITY_STATUS_VALUES with the
    code untouched -> 11 red, led by the two emits-exactly gates (section 1)
"""
import ast
import io
import pathlib
import re
import tokenize

import numpy as np
import pandas as pd
import pytest

from nmtcmapper.data.schema import ELIGIBILITY_STATUS_VALUES
from nmtcmapper.eligibility.checker import EligibilityResult, enrich_dataframe

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Every file that states the vocabulary in prose. A new site is added HERE,
# never by copying the list into the new file and hoping.
_STATEMENT_SITES = (
    "README.md",
    "docs/api.md",
    "docs/quickstart.md",
    "nmtcmapper/mapper.py",
    "nmtcmapper/eligibility/checker.py",
)

# A count word followed by the noun the enumeration is counted in. `four
# Optional[bool] columns` and `the four DECIA territories` are NOT matched — the
# nouns are wrong — and must not be, because both sit inside the paragraphs
# this gate reads.
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_COUNT_BESIDE_NOUN = re.compile(
    r"\b(" + "|".join(_COUNT_WORDS) + r"|\d+)[- ]?(outcomes?|values?|statuses|way)\b",
    re.I)
# How far (in collapsed characters) a count word may sit from the nearest
# status value and still be "beside the enumeration".
_ADJACENCY = 250

_INDETERMINATE_CONTRACT = re.compile(
    r"None`? \**exactly\** when|no row was read", re.I)


def _collapse(text):
    """Hard-wrapping is presentation. Match on one line."""
    return re.sub(r"\s+", " ", text)


def _prose_blocks_of_python(text):
    """A .py site's PROSE: every docstring, and every run of consecutive
    comment lines. Code is excluded on purpose — enrich_dataframe's ladder
    spells four of the five values as string literals within one block, which
    is a code path, not a copy of the enumeration, and is gated by execution
    in section 1."""
    tree = ast.parse(text)
    blocks = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                blocks.extend(re.split(r"\n\s*\n", doc))
    run, last = [], None
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            if last is not None and tok.start[0] != last + 1:
                blocks.append(" ".join(run))
                run = []
            run.append(tok.string.lstrip("#").strip())
            last = tok.start[0]
    if run:
        blocks.append(" ".join(run))
    return blocks


def _paragraphs(site, text):
    if site.endswith(".py"):
        blocks = _prose_blocks_of_python(text)
    else:
        blocks = re.split(r"\n\s*\n", text)
    return [_collapse(b) for b in blocks if b.strip()]


def _site_text(site):
    path = ROOT / site
    assert path.exists(), f"statement site {site} is missing — not a pass"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"statement site {site} is empty — not a pass"
    return text


# ── 1. the constant is load-bearing ───────────────────────────────────────────

def test_the_constant_is_a_tuple_of_five_distinct_strings():
    assert isinstance(ELIGIBILITY_STATUS_VALUES, tuple)
    assert len(ELIGIBILITY_STATUS_VALUES) == 5
    assert len(set(ELIGIBILITY_STATUS_VALUES)) == 5
    for v in ELIGIBILITY_STATUS_VALUES:
        assert isinstance(v, str) and v == v.strip() and v


def _result(**over):
    base = dict(
        address="x", tract_id="17031030604", nmtc_eligible=False,
        distress_level="ineligible", poverty_rate=0.197, ami_ratio=0.9127,
        unemployment_rate=0.017, is_non_metro=False, is_high_migration_rural=False,
        severe_distress=False, deep_distress=False,
        geocode_success=True, is_opportunity_zone=None, tract_found=True,
    )
    base.update(over)
    return EligibilityResult(**base)


def _every_property_path():
    """One EligibilityResult per branch of the property's ladder."""
    miss = dict(nmtc_eligible=None, distress_level="unknown", tract_found=False,
                poverty_rate=None, ami_ratio=None, unemployment_rate=None,
                is_non_metro=None, is_high_migration_rural=None,
                severe_distress=None, deep_distress=None)
    return [
        _result(nmtc_eligible=True, distress_level="lic"),
        _result(nmtc_eligible=False),
        _result(**miss),                                   # plain miss
        _result(tract_id="66010950100", **miss),           # Guam — territory
        _result(tract_id=None, geocode_success=False, **miss),
    ]


def _every_enrich_path(sample_table):
    df = pd.DataFrame({"tract_id": [
        "17031840100",   # eligible
        "17031010100",   # in table, ineligible
        "99999999999",   # syntactically valid, absent -> plain miss
        "66010950100",   # Guam -> territory
        np.nan,          # no tract resolved
    ]})
    return enrich_dataframe(df, sample_table, tract_col="tract_id")


def test_the_property_emits_exactly_the_enumeration():
    results = _every_property_path()
    assert len(results) == 5
    emitted = {r.eligibility_status for r in results}
    assert emitted == set(ELIGIBILITY_STATUS_VALUES)


def test_enrich_dataframe_emits_exactly_the_enumeration(sample_table):
    out = _every_enrich_path(sample_table)
    assert len(out) == 5
    assert set(out["eligibility_status"]) == set(ELIGIBILITY_STATUS_VALUES)


def _indeterminate_statuses(sample_table):
    """The statuses under which nmtc_eligible is None — DERIVED from what the
    code does on every path, so the doc gate below checks the docs against
    behaviour rather than against a second hand-typed list."""
    out = _every_enrich_path(sample_table)
    assert len(out) == 5
    by_prop = {r.eligibility_status: r.nmtc_eligible
               for r in _every_property_path()}
    by_enrich = dict(zip(out["eligibility_status"], out["nmtc_eligible"]))
    assert by_prop == by_enrich, "the two status ladders disagree on None"
    return frozenset(s for s, v in by_enrich.items() if v is None)


def test_the_indeterminate_subset_is_three_of_the_five(sample_table):
    ind = _indeterminate_statuses(sample_table)
    assert len(ind) == 3
    assert ind < set(ELIGIBILITY_STATUS_VALUES)
    # Both verdict statuses carry a bool; nothing else does.
    assert set(ELIGIBILITY_STATUS_VALUES) - ind == {
        "verified-eligible", "verified-ineligible"}


_FOUR_BOOLS = ("is_non_metro", "is_high_migration_rural",
               "severe_distress", "deep_distress")


def test_the_biconditional_holds_on_every_status(sample_table):
    """The README's contract sentence, checked as a biconditional on all five
    statuses before the sentence is trusted: the four Optional[bool] columns
    are None EXACTLY when the status is indeterminate — None on every
    indeterminate row, a bool on every verdict row."""
    ind = _indeterminate_statuses(sample_table)
    out = _every_enrich_path(sample_table)
    assert len(out) == 5
    assert len(_FOUR_BOOLS) == 4
    # Column access, not iterrows(): a row Series re-infers dtype and turns
    # None into NaN, which would make this gate report the frame wrongly.
    for i in range(len(out)):
        status = out["eligibility_status"].iloc[i]
        vals = [out[c].iloc[i] for c in _FOUR_BOOLS]
        if status in ind:
            assert vals == [None] * 4, (status, vals)
        else:
            assert vals == [bool(v) for v in vals], (status, vals)
    for r in _every_property_path():
        vals = [getattr(r, c) for c in _FOUR_BOOLS]
        if r.eligibility_status in ind:
            assert vals == [None] * 4, (r.eligibility_status, vals)
        else:
            assert vals == [bool(v) for v in vals], (r.eligibility_status, vals)


# ── 2. every statement site names every value ─────────────────────────────────

@pytest.mark.parametrize("site", _STATEMENT_SITES)
def test_every_statement_site_names_every_value(site):
    """MUTATION: delete `not-covered-territory` from README.md's opening list
    (README.md:16) -> red here for README.md, green elsewhere."""
    text = " ".join(_paragraphs(site, _site_text(site)))
    assert len(ELIGIBILITY_STATUS_VALUES) == 5
    missing = [v for v in ELIGIBILITY_STATUS_VALUES if v not in text]
    assert not missing, f"{site} never states {missing}"


@pytest.mark.parametrize("site", _STATEMENT_SITES)
def test_the_enumeration_is_stated_in_full_somewhere_in_each_site(site):
    """Naming every value SOMEWHERE in a file is weaker than listing them
    together: a site could mention the fifth value in a footnote and still
    carry a four-item list. At least one paragraph per site must carry the
    whole enumeration, and every paragraph that carries most of it must carry
    all of it — a four-of-five list is exactly the stale-copy shape."""
    paragraphs = _paragraphs(site, _site_text(site))
    assert len(paragraphs) >= 3, f"{site} split into {len(paragraphs)} paragraphs"
    listing = [p for p in paragraphs
               if sum(v in p for v in ELIGIBILITY_STATUS_VALUES) >= 4]
    assert listing, f"{site}: no paragraph lists the enumeration at all (j4)"
    partial = [p[:160] for p in listing
               if not set(ELIGIBILITY_STATUS_VALUES) <= {v for v in ELIGIBILITY_STATUS_VALUES if v in p}]
    assert not partial, f"{site}: stale partial enumeration(s): {partial}"


@pytest.mark.parametrize("site", _STATEMENT_SITES)
def test_no_count_word_beside_the_enumeration_disagrees_with_it(site):
    """"names the four outcomes explicitly — a / b / c / d / e". The count word
    is the shape most likely to be missed when a value is added, because it is
    not one of the values being added.

    MUTATION: README.md:14 "five outcomes" -> "four outcomes" -> red here for
    README.md, green elsewhere."""
    text = " ".join(_paragraphs(site, _site_text(site)))
    positions = [m.start() for v in ELIGIBILITY_STATUS_VALUES
                 for m in re.finditer(re.escape(v), text)]
    assert positions, f"{site} carries no status value at all (j4)"
    beside = []
    for m in _COUNT_BESIDE_NOUN.finditer(text):
        near = min(abs(p - m.start()) for p in positions)
        if near <= _ADJACENCY:
            beside.append(m)
    # This gate is only evidence where a count word exists; the README's
    # opening paragraph and the property docstring both carry one.
    if site in ("README.md", "nmtcmapper/eligibility/checker.py"):
        assert beside, f"{site}: no count word beside the enumeration (j4)"
    wrong = []
    for m in beside:
        word = m.group(1).lower()
        n = _COUNT_WORDS.get(word) or int(word)
        if n != len(ELIGIBILITY_STATUS_VALUES):
            wrong.append(text[max(0, m.start() - 40): m.end() + 60])
    assert not wrong, f"{site}: stale count word beside the enumeration: {wrong}"


# ── 3. the indeterminate contract names every indeterminate status ────────────

@pytest.mark.parametrize("site", _STATEMENT_SITES)
def test_every_none_exactly_when_sentence_names_every_indeterminate_status(
        site, sample_table):
    """The biconditional is the documented way to find indeterminate rows. If
    it names a proper subset, the filter it licenses drops the rest, and the
    surrounding prose then reads their absence as a supportable NO — the
    fabricated-negative class relocated from code into documentation.

    Only paragraphs that state the contract AND name at least one status are
    held to it; a paragraph that describes the condition in words alone
    ("the tract is absent from the table") licenses no `isin([...])`.

    MUTATION: drop `not-covered-territory` from README.md's "None exactly
    when" sentence -> red here for README.md."""
    ind = _indeterminate_statuses(sample_table)
    assert len(ind) == 3
    paragraphs = _paragraphs(site, _site_text(site))
    contract = [p for p in paragraphs
                if _INDETERMINATE_CONTRACT.search(p)
                and sum(v in p for v in ELIGIBILITY_STATUS_VALUES) >= 1]
    # The README and mapper.py are where the sentence lives; the others may
    # legitimately not restate it, but where it IS stated it must be whole.
    if site in ("README.md", "nmtcmapper/mapper.py"):
        assert len(contract) >= 1, f"{site}: contract sentence not located (j4)"
    incomplete = []
    for p in contract:
        missing = sorted(v for v in ind if v not in p)
        if missing:
            incomplete.append((missing, p[:200]))
    assert not incomplete, f"{site}: contract names a proper subset: {incomplete}"
