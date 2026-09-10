"""Item 1 (0.6.0 hygiene) — territory tracts are NOT COVERED, not "not found".

The NMTC LIC table this package loads is built on the 2016-2020 ACS, whose
universe is the 50 states + DC + Puerto Rico. The four DECIA territories
(American Samoa 60, Guam 66, Northern Mariana Islands 69, US Virgin Islands 78)
are structurally outside it — measured live against the real CDFI Fund file:

    60 American Samoa       0
    66 Guam                 0
    69 N. Mariana Islands   0
    78 US Virgin Islands    0
    72 Puerto Rico        981     <- covered, and the reason 72 is NOT in the set
    total rows         85,395

Reporting those tracts as ``not-found`` ("tract not in eligibility table",
"no match / tract absent") describes a LOOKUP MISS and invites a retry. There is
nothing to retry: the remedy is a DIFFERENT FILE, the CDFI Fund's "NMTC
Low-Income Community Census Tracts (2020 Island Areas Decennial Census)", which
this package does not load. These gates hold the output to the standard the
Connecticut refusal already meets — cause and remedy, at the point of failure.

This is still an INDETERMINATE result: ``nmtc_eligible`` stays None throughout.
"""
import pandas as pd
import pytest

from nmtcmapper.data.schema import DECIA_TERRITORY_STATE_FIPS
from nmtcmapper.eligibility.checker import EligibilityResult, enrich_dataframe

# One real tract per jurisdiction, all four confirmed present in the OZ 2.0
# universe by probe_territories.py (133 territory tracts live) and confirmed
# ABSENT from the NMTC eligibility table by the measurement quoted above.
TERRITORY_GEOIDS = {
    "60010950100": "American Samoa",
    "66010950100": "Guam",
    "69085950100": "Northern Mariana Islands",
    "78010970100": "US Virgin Islands",
}

PUERTO_RICO_GEOID = "72001956300"   # 72 IS covered by the loaded table
ABSENT_NON_TERRITORY_GEOID = "99999999999"   # syntactically valid, plain miss

# The OZ 2.0 verdicts probe_territories.py got back LIVE for these same GEOIDs.
# Carried into the fixtures so the rendered block under test is the block a real
# territory tract produces — the OZ 2.0 half is correct today and stays correct.
LIVE_OZ2 = {
    "60010950100": True, "66010950100": True,
    "69085950100": True, "78010970100": False,
}


def _not_found_result(tract_id, **over):
    """An EligibilityResult shaped exactly as a table miss produces one.

    Every one of the nine eligibility fields is None — the new status changes
    the DESCRIPTION of the indeterminacy, never the verdict.
    """
    base = dict(
        address="x", tract_id=tract_id, nmtc_eligible=None,
        distress_level="unknown", poverty_rate=None, ami_ratio=None,
        unemployment_rate=None, is_non_metro=None, is_high_migration_rural=None,
        severe_distress=None, deep_distress=None,
        geocode_success=True, is_opportunity_zone=None, tract_found=False,
    )
    base.update(over)
    return EligibilityResult(**base)


# ── the constant is a coverage boundary, not a guess ──────────────────────────

def test_decia_constant_is_the_four_territories_and_excludes_puerto_rico():
    assert DECIA_TERRITORY_STATE_FIPS == frozenset({"60", "66", "69", "78"})
    # The whole point: PR is INSIDE the loaded table's universe (981 rows).
    assert "72" not in DECIA_TERRITORY_STATE_FIPS


# ── status: both ladders, all four jurisdictions ──────────────────────────────

@pytest.mark.parametrize("geoid,name", sorted(TERRITORY_GEOIDS.items()))
def test_territory_tract_status_is_not_covered_from_property(geoid, name):
    r = _not_found_result(geoid)
    assert r.eligibility_status == "not-covered-territory", name
    assert r.nmtc_eligible is None, name


@pytest.mark.parametrize("geoid,name", sorted(TERRITORY_GEOIDS.items()))
def test_territory_tract_status_is_not_covered_from_enrich_dataframe(
    geoid, name, sample_table
):
    """The SECOND, independent status ladder.

    If only the property is fixed, check_address() says not-covered-territory
    while enrich_dataframe() says not-found for the same GEOID. Both sites.
    """
    out = enrich_dataframe(
        pd.DataFrame({"tract_id": [geoid]}), sample_table, tract_col="tract_id"
    )
    assert out["eligibility_status"].iloc[0] == "not-covered-territory", name
    assert out["nmtc_eligible"].iloc[0] is None, name


# ── Puerto Rico is the gate proving this is coverage, not FIPS vibes ──────────

def test_puerto_rico_is_not_treated_as_a_not_covered_territory():
    r = _not_found_result(PUERTO_RICO_GEOID)
    assert r.eligibility_status == "not-found"


def test_puerto_rico_is_not_not_covered_in_enrich_dataframe(sample_table):
    out = enrich_dataframe(
        pd.DataFrame({"tract_id": [PUERTO_RICO_GEOID]}),
        sample_table, tract_col="tract_id",
    )
    assert out["eligibility_status"].iloc[0] == "not-found"


# ── the new branch has not swallowed the old one ──────────────────────────────

def test_plain_absent_tract_still_reports_not_found():
    r = _not_found_result(ABSENT_NON_TERRITORY_GEOID)
    assert r.eligibility_status == "not-found"


def test_plain_absent_tract_still_reports_not_found_in_enrich_dataframe(sample_table):
    out = enrich_dataframe(
        pd.DataFrame({"tract_id": [ABSENT_NON_TERRITORY_GEOID]}),
        sample_table, tract_col="tract_id",
    )
    assert out["eligibility_status"].iloc[0] == "not-found"


# ── ordering: geocode failure still wins over the territory branch ────────────

def test_territory_tract_that_failed_to_geocode_still_reports_geocode_failed():
    r = _not_found_result("60010950100", geocode_success=False)
    assert r.eligibility_status == "geocode-failed"


# ── the rendering gate — what a user actually reads ───────────────────────────

def _summary_out(capsys, geoid):
    _not_found_result(geoid, is_oz2_nomination_eligible=LIVE_OZ2.get(geoid)).summary()
    out = capsys.readouterr().out
    # (j4) a search over an empty haystack must not pass by vacuity.
    assert out.strip(), "summary() rendered nothing; the gate below would be vacuous"
    assert "NMTC Eligible:" in out
    return out


def _nmtc_block(out):
    """The NMTC half of the rendered page — Eligible line through Description.

    The absence gates are scoped HERE, not to the whole page, for a reason: the
    OZ 2.0 and Rural lines carry their own, correct "tract absent from
    Treasury's universe" wording about a DIFFERENT table, and those lines are
    explicitly out of scope. A whole-page absence gate would either fail on
    correct text or pressure someone into editing it.
    """
    lines = out.splitlines()
    start = next(i for i, ln in enumerate(lines) if "NMTC Eligible:" in ln)
    end = next(i for i, ln in enumerate(lines) if "Poverty Rate:" in ln)
    block = "\n".join(lines[start:end])
    assert block.strip(), "NMTC block empty; the gates below would be vacuous"
    return block


def test_summary_for_a_territory_names_the_island_areas_file(capsys):
    out = _summary_out(capsys, "60010950100")
    block = _nmtc_block(out)
    # PRESENCE — cause and remedy, at the point of failure.
    assert "NOT COVERED" in block
    assert "American Samoa" in block
    assert "2016-2020 ACS" in block
    assert "50 states + DC + PR" in block
    # The file name must survive on ONE line: it is the remedy, and a user has
    # to be able to copy it out and search for it.
    assert "2020 Island Areas Decennial Census" in block
    assert any(
        "2020 Island Areas Decennial Census" in ln for ln in block.splitlines()
    ), "the Island Areas file name is split across a line break"
    # ABSENCE — the lookup-miss language this finding exists to remove.
    assert "tract absent" not in block
    assert "tract not in eligibility table" not in block
    assert "no match" not in block
    # Still indeterminate: never a fabricated negative.
    assert "❌ NO" not in block


@pytest.mark.parametrize("geoid,name", sorted(TERRITORY_GEOIDS.items()))
def test_summary_names_the_jurisdiction_not_the_fips_code(capsys, geoid, name):
    out = _summary_out(capsys, geoid)
    assert name in out, f"{geoid} should name {name}"


def test_summary_description_line_is_the_coverage_wording(capsys):
    out = _summary_out(capsys, "66010950100")
    desc = [ln for ln in out.splitlines() if ln.strip().startswith("Description:")][0]
    assert "Not covered" in desc
    assert "NOT a lookup miss" in desc
    assert "Indeterminate — eligibility not verified" not in desc


def test_summary_leaves_distress_level_unknown(capsys):
    """distress_level is a vocabulary about NMTC economic distress.

    A coverage boundary is not a distress finding; overloading it would push a
    non-distress value into every consumer that switches on distress.
    """
    r = _not_found_result("69085950100")
    assert r.distress_level == "unknown"
    r.summary()
    out = capsys.readouterr().out
    assert "Distress Level:   UNKNOWN" in out


# ── two-sided anchor: pre-image gone, post-image present ──────────────────────

def test_anchor_territory_block_replaces_the_lookup_miss_block(capsys):
    """The exact strings a territory tract rendered BEFORE this change.

    Pre-image (0.6.0 as shipped, for 60010950100):
        NMTC Eligible:    ❓ UNKNOWN — tract not in eligibility table ...
        Description:      Indeterminate — eligibility not verified (no match / tract absent)
    """
    pre_elig = "❓ UNKNOWN — tract not in eligibility table"
    pre_desc = "Indeterminate — eligibility not verified (no match / tract absent)"
    post_elig = "🚫 NOT COVERED"
    post_desc = "Not covered — outside this table's universe, NOT a lookup miss"

    block = _nmtc_block(_summary_out(capsys, "78010970100"))
    assert post_elig in block          # post-image present
    assert post_desc in block
    assert pre_elig not in block       # pre-image absent
    assert pre_desc not in block

    # ...and the pre-image is STILL what a plain absent tract renders, so the
    # anchor proves a redirect, not a deletion.
    plain = _nmtc_block(_summary_out(capsys, ABSENT_NON_TERRITORY_GEOID))
    assert pre_elig in plain
    assert pre_desc in plain
    assert post_elig not in plain


# ── out of scope for this round: OZ 2.0 / rural answers must not move ─────────

def test_territory_oz2_and_rural_paths_are_untouched():
    """Territory tracts get real, correct OZ 2.0 answers today (verified live).

    Nothing in this item may perturb them.
    """
    r = _not_found_result("60010950100", is_oz2_nomination_eligible=True)
    assert r.oz2_nomination_status == "eligible-for-nomination"
    r2 = _not_found_result("78010970100", is_oz2_nomination_eligible=False)
    assert r2.oz2_nomination_status == "ineligible-on-treasury-inputs"
