"""The `repo` marker is pinned in BOTH directions, by collection.

WHY THIS FILE EXISTS. Release run #9 for 0.6.0 failed all eight test-wheel /
test-sdist matrix jobs with `26 failed, 295 passed, 6 errors`, and no shipped
code was wrong. Those jobs run the suite from a directory holding only tests/,
pyproject.toml and README.md -- deliberately, because that exclusion is what
makes them prove the wheel and the tarball rather than the checkout -- and
five gates resolved `Path(__file__).resolve().parent.parent` as the repo root
and reached for docs/, tools/, CHANGELOG.md and nmtcmapper/*.py that were not
there. Every one of those gates is an assertion about the REPOSITORY, not the
artifact, so the fix was to mark them `repo` and have release.yml deselect
them with `-m "not live and not repo"`.

A marker is a deselection, and a deselection is the vacuity class this suite
exists to hunt: `-m "not repo"` becomes `-m "not everything"` the first time a
module-level `pytestmark = pytest.mark.repo` lands on the wrong file, and the
release jobs stay green having tested nothing. So the marked set is pinned as
an EXACT set here, not a floor alone:

  * every gate that reads a repo-only path must be marked (or the release
    jobs fail again the way #9 did);
  * every marked gate must be one this file names (or a stray mark silently
    removes real coverage from the artifact gates);
  * the count clears a floor derived from today's set, the way
    test_oz2_vacuity.py floors its loops -- so emptying this file's list and
    the marks together still reddens;
  * every module that computes the repo root either carries the marker or is
    allow-listed here with the reason it need not.

WHAT IS AND IS NOT `repo`. README.md and pyproject.toml ship beside tests/ in
EVERY layout -- the checkout, the sdist (MANIFEST.in), and the test-wheel job,
which copies both -- and test_constraints.py asserts README.md's presence
rather than skipping on it. A gate reading only those two is a gate about the
artifact and stays unmarked. docs/, tools/, CHANGELOG.md and nmtcmapper/*.py
are NOT in the run directory of either release job, and a gate reading any of
them has no meaning against an installed wheel.

HOW THE SET IS READ. `pytest --collect-only -q -m repo` in a subprocess from
the directory above tests/, the same way tools/docs_check.py reads the README's
test-count claims. That is the exact selection release.yml's `-m` expression
acts on, and it does not depend on how THIS test was invoked -- run this file
alone and it still sees the whole suite.

MUTATIONS, each verified red:
  * remove `pytestmark` from test_docs_check_tool.py -> red at
    test_every_expected_repo_gate_is_marked (6 nodeids missing)
  * add `pytestmark = pytest.mark.repo` to test_mapper.py -> red at
    test_no_gate_is_marked_repo_that_this_file_does_not_name
  * empty EXPECTED_REPO_GATES and strip every mark -> red at
    test_the_repo_marked_set_clears_its_floor
  * a new module computing `.parent.parent` with no mark and no allow-list
    entry -> red at test_every_module_that_computes_the_repo_root_is_accounted_for

NOT `repo` ITSELF: this file reads only tests/ and pytest's own collection, so
it runs -- and means the same thing -- in every layout, including the release
jobs, where it proves the deselected set is exactly the pinned one.
"""
import pathlib
import re
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent  # the directory pytest is run from in every layout

# module -> the gates in it that read a repo-only path, and which path.
# Function names, not nodeids: a parametrized gate over five statement sites is
# one decision, not five, and adding a sixth site must not move this list.
EXPECTED_REPO_GATES = {
    "test_status_enumeration.py": {
        # _STATEMENT_SITES: docs/api.md, docs/quickstart.md, nmtcmapper/mapper.py,
        # nmtcmapper/eligibility/checker.py (README.md too, but the other four
        # are repo-only, and the gate is one decision across all five)
        "test_every_statement_site_names_every_value",
        "test_the_enumeration_is_stated_in_full_somewhere_in_each_site",
        "test_no_count_word_beside_the_enumeration_disagrees_with_it",
        "test_every_none_contract_paragraph_names_every_indeterminate_status",
        # CHANGELOG.md
        "test_upgrading_names_the_additive_status_and_the_corrected_membership_test",
    },
    "test_docs_check_tool.py": {
        # every test loads tools/docs_check.py through the module-scoped `tool`
        # fixture, and the last one reads its source as well
        "test_the_fixture_suite_collects_two_tests_cleanly",
        "test_a_collection_error_fails_the_gate_even_when_a_count_parses",
        "test_a_marker_that_selects_nothing_is_zero_not_an_error",
        "test_a_pattern_without_a_capture_group_is_a_named_finding",
        "test_the_readmes_own_numbers_are_cross_checked",
        "test_a_lost_live_marker_is_not_detectable_by_collection_and_the_tool_says_so",
        "test_the_fourth_claim_is_checked_against_its_own_marker",
    },
    "test_forward_promises.py": {
        # _doc_pages(): README.md + docs/*.md, floored at four pages
        "test_no_shipped_doc_promises_the_version_being_built",
        "test_the_scan_actually_read_versions_somewhere",
    },
    "test_oz2.py": {
        # _DOC_FILES = README.md + CHANGELOG.md
        "test_no_oz2_figure_is_hand_typed",
        "test_oz2_prose_never_calls_an_eligible_tract_designated",
        "test_oz2_prose_does_not_say_the_window_closes_in_september",
        "test_column_two_is_never_called_the_lic_column_without_its_qualifier",
        # nmtcmapper/**/*.py and CHANGELOG.md
        "test_the_retired_nmtc_vocabulary_never_appears",
    },
    "test_oz2_vacuity.py": {
        # both read T._DOC_FILES from the repo root
        "test_the_prose_gates_actually_found_oz2_paragraphs_to_check",
        "test_the_figure_gate_actually_examined_some_figures",
    },
}

# Derived from EXPECTED_REPO_GATES as it stands today (21 functions), the way
# test_oz2_vacuity.py floors its loops at the count they carry. Re-derive when
# the list resizes; a floor that sits at zero would let the marks and the list
# vanish together.
REPO_GATE_FLOOR = 21

# Modules that compute the repo root (`.resolve().parent.parent`) and carry NO
# repo mark, each with the reason that is correct. README.md ships in every
# layout and is asserted present, not skipped on.
ROOT_READERS_THAT_ONLY_READ_SHIPPED_FILES = {
    "test_constraints.py": "reads README.md only (test_c1b_the_readme_and_the_docstring_draw_the_same_tree)",
    "test_repo_marker.py": "this file: reads tests/ and pytest's own collection only",
}


def _collect(marker_expr):
    """Node ids pytest selects for `-m marker_expr`, from the directory above
    tests/ -- the cwd of every layout that runs this suite."""
    cmd = [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q",
           "-p", "no:cacheprovider", "-m", marker_expr]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    # exit 5 is "no tests collected" -- a legitimate answer of "none", which
    # the floor below then refuses. Anything else means the collection is
    # not trustworthy, and a set read out of it certifies nothing.
    assert proc.returncode in (0, 5), (
        f"pytest --collect-only -m {marker_expr!r} exited {proc.returncode}:\n"
        f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    ids = [ln.strip() for ln in proc.stdout.splitlines() if "::" in ln]
    return ids


def _functions(nodeids):
    """{module: {function}} with parametrize ids stripped."""
    out = {}
    for nid in nodeids:
        path, _, rest = nid.partition("::")
        func = re.sub(r"\[.*\]$", "", rest.split("::")[-1])
        out.setdefault(pathlib.Path(path).name, set()).add(func)
    return out


@pytest.fixture(scope="module")
def marked():
    return _functions(_collect("repo"))


@pytest.fixture(scope="module")
def unmarked():
    return _functions(_collect("not repo"))


def test_the_repo_marked_set_clears_its_floor(marked):
    """Non-empty, and at least as large as the set this file names today."""
    n = sum(len(fns) for fns in marked.values())
    assert n >= REPO_GATE_FLOOR, (
        f"only {n} functions carry @repo (floor {REPO_GATE_FLOOR}); an empty or "
        f"shrunken set means release.yml's `not repo` no longer deselects the "
        f"gates that failed run #9, or this floor was not re-derived")
    assert sum(len(v) for v in EXPECTED_REPO_GATES.values()) >= REPO_GATE_FLOOR, (
        "EXPECTED_REPO_GATES shrank below the floor without the floor moving")


@pytest.mark.parametrize("module", sorted(EXPECTED_REPO_GATES))
def test_every_expected_repo_gate_is_marked(marked, module):
    """Direction one: every gate that reads a repo-only path is deselected by
    `not repo`. Unmarked, it fails the release jobs the way run #9 did."""
    missing = EXPECTED_REPO_GATES[module] - marked.get(module, set())
    assert not missing, (
        f"{module}: {sorted(missing)} read a repo-only path but are not marked "
        f"@repo -- they will fail in release.yml's packaged layouts")


def test_no_gate_is_marked_repo_that_this_file_does_not_name(marked):
    """Direction two: a stray mark -- a module-level pytestmark on the wrong
    file -- would silently remove real artifact coverage from the release jobs
    while ci.yml stays green. Every marked gate must be named here, on purpose."""
    stray = {
        m: sorted(fns - EXPECTED_REPO_GATES.get(m, set()))
        for m, fns in marked.items()
        if fns - EXPECTED_REPO_GATES.get(m, set())
    }
    assert not stray, (
        f"marked @repo but not named in EXPECTED_REPO_GATES: {stray} -- if the "
        f"gate really reads docs/, tools/, CHANGELOG.md or nmtcmapper/*.py, add "
        f"it here with the path; otherwise remove the mark")


def test_the_two_selections_partition_the_suite(marked, unmarked):
    """`-m repo` and `-m "not repo"` are complements by construction; this
    pins that the subprocess read both sides and neither is the whole suite."""
    both = {m: marked[m] & unmarked[m] for m in marked if m in unmarked and marked[m] & unmarked[m]}
    assert not both, f"functions collected on both sides: {both}"
    assert unmarked, "`not repo` collected nothing -- the release jobs would run zero tests"
    # The artifact gates that must survive `not repo`: a sample of modules that
    # read nothing outside tests/ and are what the release jobs exist to run.
    for m in ("test_mapper.py", "test_checker.py", "test_constraints.py",
              "test_territory_coverage.py", "test_fail_loud.py"):
        assert m in unmarked, f"{m} is entirely deselected by `not repo`"


def test_every_module_that_computes_the_repo_root_is_accounted_for(marked):
    """A new gate that resolves the repo root and reads docs/ without a mark is
    exactly how run #9 happened. Every module that computes the root must be
    either marked or allow-listed here with its reason."""
    readers = sorted(
        p.name for p in HERE.glob("test_*.py")
        if re.search(r"\.parent\.parent\b", p.read_text(encoding="utf-8"))
    )
    assert len(readers) >= 6, f"the sweep found only {readers}; it is not reading the suite"
    unaccounted = [
        m for m in readers
        if m not in marked and m not in ROOT_READERS_THAT_ONLY_READ_SHIPPED_FILES
    ]
    assert not unaccounted, (
        f"{unaccounted} compute the repo root but carry no @repo mark and are "
        f"not allow-listed in ROOT_READERS_THAT_ONLY_READ_SHIPPED_FILES -- if "
        f"they read only README.md / pyproject.toml, allow-list them with the "
        f"reason; otherwise mark the gates and name them in EXPECTED_REPO_GATES")
    stale = [m for m in ROOT_READERS_THAT_ONLY_READ_SHIPPED_FILES if m not in readers]
    assert not stale, f"allow-listed but no longer compute the root: {stale}"


def test_the_repo_marker_is_registered():
    """--strict-markers turns an unregistered marker into a collection error in
    the release jobs; the registration is what makes `-m "not repo"` mean
    anything. Read from pyproject.toml, which ships in every layout."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^\s*"repo:.*not live and not repo', text, re.M), (
        "pyproject.toml [tool.pytest.ini_options].markers does not register `repo` "
        "with the release expression in its description")
