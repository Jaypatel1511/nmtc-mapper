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
    # The FULL file title must survive on ONE line: it is the remedy, and a
    # user has to be able to copy it out and search for it. FIX4 F4: this gate
    # used to assert only that the parenthetical was unbroken — narrower than
    # its own comment — while the page split the title across two lines and
    # abbreviated "New Markets Tax Credit" to "NMTC". The title is the Fund's
    # exact one, read from the schema constant, not a third copy.
    from nmtcmapper.data.schema import DECIA_ISLAND_AREAS_FILE_TITLE
    assert DECIA_ISLAND_AREAS_FILE_TITLE == (
        "New Markets Tax Credit Low-Income Community Census Tracts "
        "(2020 Island Areas Decennial Census)")
    assert DECIA_ISLAND_AREAS_FILE_TITLE in block
    assert any(
        DECIA_ISLAND_AREAS_FILE_TITLE in ln for ln in block.splitlines()
    ), "the Island Areas file title is split across a line break"
    # The abbreviation is gone: the Fund does not title the file "NMTC ...".
    assert "NMTC Low-Income Community Census Tracts" not in block
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


# ── FIX4 F1: a leading-zero-stripped MAINLAND GEOID is not a territory ────────
#
# `_decia_territory_name` sliced two characters off whatever it was handed, with
# no length check. A California GEOID out of Excel or CSV arrives with its
# leading zero gone — "06037101110" -> "6037101110", or the int 6037101110 — and
# its first two characters are then "60": American Samoa. Measured against the
# live CDFI Fund file (85,395 rows), 8,707 tracts collide this way, every one of
# them in California; 66, 69 and 78 collide with nothing, because no state +
# county pair spells 066/069/078. The guard is on SHAPE (11 digits), not on
# which prefixes happen to collide today, so all four are gated.
#
# Before 7d18d7f this input returned `not-found` — vague but true, and what
# README's Known limitations documents. These gates restore exactly that. They
# do NOT normalize (zfill) — that changes answers for every caller who gets
# `not-found` today and is 0.7.0 work with its own methodology.

# The 10-digit stripped shape for each prefix: the territory GEOID with its last
# digit lopped is a string that starts with the prefix and is not 11 long.
STRIPPED_PER_PREFIX = {geoid[:2]: geoid[:10] for geoid in TERRITORY_GEOIDS}

# Real mainland tracts from the live table, in the shape Excel/CSV emits them.
CA_STRIPPED = {
    "06037101110": "6037101110",   # Los Angeles County
    "06001400100": "6001400100",   # Alameda County
    "06075010100": "6075010100",   # San Francisco County
}
CA_STRIPPED_INT = 6037101110       # the int shape — the reason this reaches users


def test_the_stripped_shapes_actually_start_with_the_territory_prefix():
    """(j4) the gates below prove nothing if the inputs do not collide."""
    for prefix, stripped in STRIPPED_PER_PREFIX.items():
        assert stripped[:2] == prefix and len(stripped) == 10
    for full, stripped in CA_STRIPPED.items():
        assert str(int(full)) == stripped and stripped[:2] == "60"
    assert str(CA_STRIPPED_INT)[:2] == "60"
    assert len(STRIPPED_PER_PREFIX) == 4 == len(DECIA_TERRITORY_STATE_FIPS)


@pytest.mark.parametrize("prefix,name", sorted(
    (g[:2], n) for g, n in TERRITORY_GEOIDS.items()))
def test_helper_names_the_territory_only_for_an_eleven_digit_geoid(prefix, name):
    from nmtcmapper.eligibility.checker import _decia_territory_name
    full = next(g for g in TERRITORY_GEOIDS if g.startswith(prefix))
    assert _decia_territory_name(full) == name
    assert _decia_territory_name(STRIPPED_PER_PREFIX[prefix]) is None, (
        f"a 10-digit id starting {prefix} was told it is {name}")


@pytest.mark.parametrize("stripped", sorted(CA_STRIPPED.values()) + [CA_STRIPPED_INT])
def test_helper_does_not_call_a_stripped_california_tract_american_samoa(stripped):
    """MUTATION: drop the length guard in _decia_territory_name -> red here."""
    from nmtcmapper.eligibility.checker import _decia_territory_name
    assert _decia_territory_name(stripped) is None


def test_helper_rejects_every_non_geoid_shape():
    from nmtcmapper.eligibility.checker import _decia_territory_name
    for junk in ("60", "600109501", "600109501000", "6001095010.0", "60-01095010",
                 " 60010950100", "60010950100 ", "", 6001095010.0, 60):
        assert _decia_territory_name(junk) is None, repr(junk)


@pytest.mark.parametrize("stripped", sorted(CA_STRIPPED.values()) + [CA_STRIPPED_INT])
def test_stripped_california_status_is_not_found_from_property(stripped):
    r = _not_found_result(stripped)
    assert r.eligibility_status == "not-found"
    assert r.nmtc_eligible is None


@pytest.mark.parametrize("stripped", sorted(CA_STRIPPED.values()) + [CA_STRIPPED_INT])
def test_stripped_california_status_is_not_found_from_enrich_dataframe(
        stripped, sample_table):
    """The second ladder, including the int64 column Excel/CSV produce."""
    df = pd.DataFrame({"tract_id": [stripped]})
    if isinstance(stripped, int):
        assert pd.api.types.is_integer_dtype(df["tract_id"])
    out = enrich_dataframe(df, sample_table, tract_col="tract_id")
    assert out["eligibility_status"].iloc[0] == "not-found"
    assert out["nmtc_eligible"].iloc[0] is None


@pytest.mark.parametrize("prefix", sorted(STRIPPED_PER_PREFIX))
def test_stripped_shape_is_not_found_on_both_ladders_for_every_prefix(
        prefix, sample_table):
    stripped = STRIPPED_PER_PREFIX[prefix]
    assert _not_found_result(stripped).eligibility_status == "not-found"
    out = enrich_dataframe(pd.DataFrame({"tract_id": [stripped]}),
                           sample_table, tract_col="tract_id")
    assert out["eligibility_status"].iloc[0] == "not-found"


@pytest.mark.parametrize("stripped", sorted(CA_STRIPPED.values()) + [CA_STRIPPED_INT])
def test_summary_for_a_stripped_california_tract_names_no_jurisdiction(
        capsys, stripped):
    """The rendered page must carry NEITHER a jurisdiction name NOR the
    "NOT a lookup miss" sentence — for this input it IS a lookup miss."""
    _not_found_result(stripped).summary()
    out = capsys.readouterr().out
    assert out.strip() and "NMTC Eligible:" in out
    block = _nmtc_block(out)
    for name in TERRITORY_GEOIDS.values():
        assert name not in out, name
    assert "NOT a lookup miss" not in out
    assert "NOT COVERED" not in block
    assert "tract not in eligibility table" in block   # the true, vague answer


@pytest.mark.parametrize("prefix", sorted(STRIPPED_PER_PREFIX))
def test_summary_for_a_stripped_shape_names_no_jurisdiction_for_every_prefix(
        capsys, prefix):
    _not_found_result(STRIPPED_PER_PREFIX[prefix]).summary()
    out = capsys.readouterr().out
    assert out.strip() and "NMTC Eligible:" in out
    for name in TERRITORY_GEOIDS.values():
        assert name not in out, name
    assert "NOT a lookup miss" not in out


# ── Connecticut is safe by width, and is pinned so ────────────────────────────

CT_STRIPPED = "9001450101"    # "09001450101" (Fairfield County, legacy scheme)


def test_stripped_connecticut_id_does_not_take_the_refusal_branch(mapper):
    """checker.py and mapper.py slice `[:5]` against FIVE-character prefixes
    ("09001".."09015"). A stripped GEOID never starts with "0", so its first
    five characters ("90014") can never equal a legacy county prefix — the
    5-char width is what makes it safe. This gate exists so nobody later
    "simplifies" the CT check to a 2-char state slice and inherits F1."""
    from nmtcmapper.mapper import _oz2_flags
    assert str(int("09001450101")) == CT_STRIPPED and CT_STRIPPED[:5] == "90014"
    # the property ladder
    r = _not_found_result(CT_STRIPPED)
    assert r.oz2_nomination_status != "refused-connecticut-scheme"
    assert r.rural_area_qoz_status != "refused-connecticut-scheme"
    assert r.eligibility_status == "not-found"
    # the mapper's OZ 2.0 lookup
    flags = _oz2_flags(CT_STRIPPED, mapper._oz2_table)
    assert flags == {"is_oz2_nomination_eligible": None,
                     "is_rural_area_qoz_eligible": None,
                     "oz2_inputs_missing": None}
    assert mapper.check_tract(CT_STRIPPED).oz2_nomination_status == "not-determined"
    # ...while the 11-digit form still IS refused — the width guard is not a
    # loosening of the refusal.
    assert mapper.check_tract("09001450101").oz2_nomination_status == \
        "refused-connecticut-scheme"


# ── the live specimen, end to end ─────────────────────────────────────────────

@pytest.mark.live
def test_live_california_specimen_eleven_digits_verdict_ten_digits_not_found(capsys):
    """"06037101110" gets its real verdict; "6037101110" gets not-found and a
    page naming no jurisdiction — the exact pair from the F1 reproduction."""
    from nmtcmapper.mapper import NMTCMapper
    m = NMTCMapper()
    full = m.check_tract("06037101110")
    assert full.tract_found and full.eligibility_status in (
        "verified-eligible", "verified-ineligible")
    assert isinstance(full.nmtc_eligible, bool)
    stripped = m.check_tract("6037101110")
    assert stripped.eligibility_status == "not-found"
    assert stripped.nmtc_eligible is None
    stripped.summary()
    out = capsys.readouterr().out
    assert "NMTC Eligible:" in out
    for name in TERRITORY_GEOIDS.values():
        assert name not in out, name
    assert "NOT a lookup miss" not in out


# ── FIX4 F3: distress_description and summary() are ONE surface ───────────────
#
# 7d18d7f substituted the coverage wording inside summary() and left the public
# `distress_description` property (README, docs/api.md) on DISTRESS_LEVELS, so
# one object answered "Not covered — ... NOT a lookup miss" on the page and
# "Indeterminate — eligibility not verified (no match / tract absent)" from the
# property: the exact wording the CHANGELOG says was removed. The selection now
# lives in the property and summary() reads it.

def _description_line(out):
    lines = [ln for ln in out.splitlines() if ln.strip().startswith("Description:")]
    assert len(lines) == 1, out
    return lines[0].split("Description:", 1)[1].strip()


def _one_result_per_status():
    """Five results, one per eligibility_status, mirroring
    tests/test_status_enumeration.py — verdicts and all three indeterminates."""
    found = dict(
        address="x", tract_id="17031030604", nmtc_eligible=False,
        distress_level="ineligible", poverty_rate=0.197, ami_ratio=0.9127,
        unemployment_rate=0.017, is_non_metro=False,
        is_high_migration_rural=False, severe_distress=False,
        deep_distress=False, geocode_success=True, is_opportunity_zone=None,
        tract_found=True,
    )
    return {
        "verified-eligible": EligibilityResult(
            **{**found, "nmtc_eligible": True, "distress_level": "severe",
               "severe_distress": True}),
        "verified-ineligible": EligibilityResult(**found),
        "not-found": _not_found_result(ABSENT_NON_TERRITORY_GEOID),
        "not-covered-territory": _not_found_result("66010950100"),
        "geocode-failed": _not_found_result(None, geocode_success=False),
    }


def test_the_property_carries_the_coverage_wording_for_a_territory():
    from nmtcmapper.eligibility.checker import NOT_COVERED_DESCRIPTION
    r = _not_found_result("66010950100")     # live Guam tract
    assert r.eligibility_status == "not-covered-territory"
    assert r.distress_description == NOT_COVERED_DESCRIPTION
    assert "NOT a lookup miss" in r.distress_description
    assert "tract absent" not in r.distress_description
    assert "no match" not in r.distress_description
    # distress_level is untouched — it is a distress vocabulary, not coverage.
    assert r.distress_level == "unknown"


@pytest.mark.parametrize("status", sorted(_one_result_per_status()))
def test_distress_description_and_summary_agree_on_one_object(capsys, status):
    r = _one_result_per_status()[status]
    assert r.eligibility_status == status, "fixture does not produce its status"
    r.summary()
    out = capsys.readouterr().out
    assert out.strip(), "summary() rendered nothing"
    rendered = _description_line(out)
    assert rendered, "empty Description line"
    assert rendered == r.distress_description, (status, rendered, r.distress_description)


def test_non_territory_descriptions_still_come_from_the_distress_vocabulary():
    """The property change is a redirect for ONE status; the other four still
    read DISTRESS_LEVELS, including the plain miss's "Indeterminate" line."""
    from nmtcmapper.data.schema import DISTRESS_LEVELS
    for status, r in _one_result_per_status().items():
        if status == "not-covered-territory":
            continue
        assert r.distress_description == DISTRESS_LEVELS[r.distress_level], status
    assert "Indeterminate" in _not_found_result(ABSENT_NON_TERRITORY_GEOID).distress_description
