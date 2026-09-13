"""FIX4 F7 — tools/docs_check.py's test-count assertion, held to what it claims.

Three defects, all in `check_test_count`:

  1. The collection sum check `offline + live == total` could not fail: `-m X`
     and `-m "not X"` partition the collection by construction. Its comment
     claimed it caught a test that lost its `@live` mark; the re-audit set
     `live_marker` to a marker no test carries and the gate passed. The check
     is deleted; the README's OWN three numbers are still cross-checked.
  2. pytest's exit status was ignored. A collection `ImportError` prints
     "N tests collected, 1 error" and exits 2; the count parsed and the gate
     passed on a suite that could not import.
  3. A configured pattern with no capture group raised `IndexError` — a
     traceback where a named finding belongs.

The tool is a script under tools/, imported here by path. It needs tomllib
(3.11+) or `tomli`; where neither exists the tool refuses to import and these
tests skip rather than fail, exactly as the tool itself refuses to run.
"""
import importlib.util
import pathlib
import sys
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Every test here loads tools/docs_check.py, which ships in the sdist but is
# not in the run directory of either release job -- and is not in the wheel
# at all. Meaningless against an installed artifact; see the `repo` marker in
# pyproject.toml and tests/test_repo_marker.py.
pytestmark = pytest.mark.repo


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "docs_check_under_test", ROOT / "tools" / "docs_check.py")
    mod = importlib.util.module_from_spec(spec)
    # The tool uses `from __future__ import annotations` with dataclasses,
    # which resolve their annotations through sys.modules[__name__].
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except SystemExit:  # no tomllib / tomli on this interpreter
        del sys.modules[spec.name]
        pytest.skip("tools/docs_check.py needs tomllib or tomli")
    return mod


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


def _root_with(tmp_path, readme, tests):
    """A throwaway repo: README.md plus a tests/ dir of the given files."""
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    tdir = tmp_path / "tests"
    tdir.mkdir()
    (tdir / "__init__.py").write_text("")
    for name, body in tests.items():
        (tdir / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


GOOD = """
    import pytest
    def test_a(): pass
    @pytest.mark.live
    def test_b(): pass
"""
BROKEN = """
    import a_module_that_does_not_exist_anywhere
    def test_c(): pass
"""
CLAIM = r"^(\d+)\s+tests\b"


def test_the_fixture_suite_collects_two_tests_cleanly(tool, tmp_path):
    """(j4) the fixtures below prove nothing if the good suite does not
    collect as expected on this interpreter."""
    root = _root_with(tmp_path, "2 tests\n", {"test_good.py": GOOD})
    count, tail, rc = tool._collect_count(root, "tests", None)
    assert (count, rc) == (2, 0), tail
    report = tool.Report()
    tool.check_test_count(root, "2 tests\n", "tests", {"claim_pattern": CLAIM}, report)
    assert report.ids == [], report.findings


# ── 2. exit status ────────────────────────────────────────────────────────────

def test_a_collection_error_fails_the_gate_even_when_a_count_parses(tool, tmp_path):
    """MUTATION: drop the returncode check in check_test_count -> red here:
    pytest prints "2 tests collected, 1 error" (parseable), exits 2, and the
    README's claim of 2 "matches"."""
    root = _root_with(tmp_path, "2 tests\n",
                      {"test_good.py": GOOD, "test_broken.py": BROKEN})
    count, tail, rc = tool._collect_count(root, "tests", None)
    assert rc != 0, "fixture did not produce a collection error"
    assert count == 2, tail   # the count parses — that is the trap
    report = tool.Report()
    tool.check_test_count(root, "2 tests\n", "tests", {"claim_pattern": CLAIM}, report)
    assert "readme-test-count-collect" in report.ids, report.findings
    msg = [f.message for f in report.findings if f.fid == "readme-test-count-collect"][0]
    assert "exit" in msg and "2" in msg


def test_a_marker_that_selects_nothing_is_zero_not_an_error(tool, tmp_path):
    """pytest exits 5 for "no tests collected"; that is a count of 0, not a
    broken suite, and it stays so."""
    root = _root_with(tmp_path, "x", {"test_good.py": GOOD})
    count, tail, rc = tool._collect_count(root, "tests", "nonexistent_marker")
    assert count == 0, tail
    report = tool.Report()
    tool.check_test_count(
        root, "2 tests\n0 of these are live\n", "tests",
        {"claim_pattern": CLAIM, "live_claim_pattern": r"^(\d+) of these are live",
         "live_marker": "nonexistent_marker"}, report)
    assert "readme-test-count-collect" not in report.ids, report.findings


# ── 3. a pattern with no capture group ────────────────────────────────────────

def test_a_pattern_without_a_capture_group_is_a_named_finding(tool, tmp_path):
    """MUTATION: remove the `.groups` check -> IndexError traceback here."""
    root = _root_with(tmp_path, "2 tests\n", {"test_good.py": GOOD})
    report = tool.Report()
    tool.check_test_count(root, "2 tests\n", "tests",
                          {"claim_pattern": r"^\d+\s+tests\b"}, report)
    assert "readme-test-count-pattern" in report.ids, report.findings
    msg = [f.message for f in report.findings if f.fid == "readme-test-count-pattern"][0]
    assert "capture group" in msg and "claim_pattern" in msg


# ── 1. the sum check says what it does ────────────────────────────────────────

def test_the_readmes_own_numbers_are_cross_checked(tool, tmp_path):
    """The one sum check that CAN fail: the README's three stated numbers
    against each other. 2 total, 1 live, 2 offline does not sum."""
    root = _root_with(tmp_path, "x", {"test_good.py": GOOD})
    readme = "2 tests\n1 of these are live\nleaving 2 offline\n"
    cfg = {"claim_pattern": CLAIM,
           "live_claim_pattern": r"^(\d+) of these are live",
           "offline_claim_pattern": r"^leaving (\d+) offline"}
    report = tool.Report()
    tool.check_test_count(root, readme, "tests", cfg, report)
    assert "readme-test-count-sum" in report.ids, report.findings
    assert "readme-test-count-offline" in report.ids   # claims 2, collects 1
    msg = [f.message for f in report.findings if f.fid == "readme-test-count-sum"][0]
    assert "README's own numbers" in msg


def test_a_lost_live_marker_is_not_detectable_by_collection_and_the_tool_says_so(
        tool, tmp_path):
    """The re-audit's disproof, pinned: with a marker no test carries and only
    the total claimed, the gate passes — `-m X` and `-m "not X"` are
    complements, so no collection-level sum can ever disagree. The comment in
    the tool must not claim otherwise; this test holds the source to it."""
    root = _root_with(tmp_path, "2 tests\n", {"test_good.py": GOOD})
    report = tool.Report()
    tool.check_test_count(root, "2 tests\n", "tests",
                          {"claim_pattern": CLAIM, "live_marker": "nonexistent"},
                          report)
    assert report.ids == [], report.findings
    src = (ROOT / "tools" / "docs_check.py").read_text(encoding="utf-8")
    assert "offline + live != total" not in src, (
        "the tautological collection sum check is back")
    assert "lost its `@live` mark" not in src, (
        "the comment overclaims a check that cannot fail")


# ── 5. the fourth claim: repo-only gates ──────────────────────────────────────

REPO_SPLIT = """
    import pytest
    def test_a(): pass
    @pytest.mark.live
    def test_b(): pass
    @pytest.mark.repo
    def test_c(): pass
    @pytest.mark.repo
    def test_d(): pass
"""


def test_the_fourth_claim_is_checked_against_its_own_marker(tool, tmp_path):
    """FIX5: the README states how many gates are `@repo` -- the ones
    release.yml deselects in its packaged layouts -- and that number is a claim
    like the other three: collected with `-m <repo_marker>`, compared, and a
    configured pattern that matches nothing is a failure.

    Red proof: 2 tests carry @repo; the README claims 1 -> readme-test-count-repo.
    Then the README claims 2 -> no finding. Then the pattern is configured but
    the README has no such sentence -> readme-test-count-repo, naming the key.
    """
    root = _root_with(tmp_path, "x", {"test_split.py": REPO_SPLIT})
    cfg = {"claim_pattern": CLAIM,
           "live_claim_pattern": r"^(\d+) of these are live",
           "offline_claim_pattern": r"^leaving (\d+) offline",
           "repo_claim_pattern": r"^(\d+) of the offline tests are repo",
           "live_marker": "live", "repo_marker": "repo"}

    wrong = "4 tests\n1 of these are live\nleaving 3 offline\n1 of the offline tests are repo\n"
    report = tool.Report()
    tool.check_test_count(root, wrong, "tests", cfg, report)
    assert "readme-test-count-repo" in report.ids, report.findings
    msg = [f.message for f in report.findings if f.fid == "readme-test-count-repo"][0]
    assert "claims 1 repo" in msg and "collects 2" in msg, msg
    # the other three claims are right, so only the fourth fires
    assert report.ids == ["readme-test-count-repo"], report.findings

    right = wrong.replace("1 of the offline", "2 of the offline")
    report = tool.Report()
    tool.check_test_count(root, right, "tests", cfg, report)
    assert report.ids == [], report.findings

    # the marker is read from the config, not assumed: a repo_marker no test
    # carries collects 0, and the claim of 2 then fails as a mismatch
    report = tool.Report()
    tool.check_test_count(root, right, "tests", dict(cfg, repo_marker="other"), report)
    assert "readme-test-count-repo" in report.ids, report.findings

    # configured but absent from the README: the claim moved, the gate says so
    report = tool.Report()
    tool.check_test_count(root, "4 tests\n1 of these are live\nleaving 3 offline\n",
                          "tests", cfg, report)
    assert "readme-test-count-repo" in report.ids, report.findings
    msg = [f.message for f in report.findings if f.fid == "readme-test-count-repo"][0]
    assert "repo_claim_pattern" in msg and "matches nothing" in msg, msg
