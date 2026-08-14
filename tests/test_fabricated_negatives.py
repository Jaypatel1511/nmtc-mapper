"""0.5.0 — the fabricated-negative contract.

0.4.0 built a tri-state contract for the verdict and left its neighbours
fabricating inside the very branches it was written to protect: the lookup-miss
branch of ``check_tract()`` and the geocode-no-match branch of ``check_address()``
set six booleans to a confident ``False`` about a tract that was never read.

These tests pin the remedy, in both directions — the ``None``s that must appear
on the two indeterminate branches, AND the ``False``s that must NOT move for a
found tract, because those are the Fund's published ``NO``.

Offline throughout except the ``@live`` block at the end, which pins the
partition the release's headline rests on against the real 85,395-row file.
"""
import pandas as pd
import pytest

from nmtcmapper.data.loader import load_eligibility_table, _compute_eligibility
from nmtcmapper.eligibility.checker import (
    EligibilityResult, check_tract, enrich_dataframe,
)
from nmtcmapper.mapper import NMTCMapper


# ── the two indeterminate branches return None, not False ────────────────────

TRACT_DERIVED = (
    "is_non_metro", "is_high_migration_rural", "severe_distress", "deep_distress",
)


def test_lookup_miss_returns_none_for_every_tract_derived_boolean(mapper):
    """check_tract()'s miss branch. Through 0.4.3 all four were False — a claim
    about a tract for which no row was ever read."""
    r = mapper.check_tract("99999999999")
    assert r.eligibility_status == "not-found"
    assert r.tract_found is False
    for field in TRACT_DERIVED:
        assert getattr(r, field) is None, field
        assert getattr(r, field) is not False, field


def test_geocode_no_match_returns_none_for_every_boolean(mapper, monkeypatch):
    """check_address()'s no-match branch fabricated a SIXTH negative that the
    lookup-miss branch does not: with no GEOID in hand there is nothing to test
    OZ membership against either."""
    monkeypatch.setattr("nmtcmapper.mapper.geocode_address", lambda a: None)
    r = mapper.check_address("nowhere at all, XX")
    assert r.eligibility_status == "geocode-failed"
    for field in TRACT_DERIVED:
        assert getattr(r, field) is None, field
    assert r.is_opportunity_zone is None
    assert r.opportunity_zone_status == "no-tract"


def test_a_found_tracts_false_is_unchanged(mapper):
    """THE OTHER DIRECTION, and the one that is easy to over-correct. For a found
    tract a False is the Fund's published NO — all five source columns are strict
    YES/NO across all 85,395 rows with zero blanks, including the 2,750 rows with
    null demographics. Those Falses stay False, never None."""
    r = mapper.check_tract("17031010100")
    assert r.tract_found is True
    for field in TRACT_DERIVED:
        v = getattr(r, field)
        assert v is not None, field
        assert isinstance(v, bool), field
    assert r.severe_distress is False
    assert r.deep_distress is False


# ── is_opportunity_zone: True or None, never False ───────────────────────────

def test_opportunity_zone_is_never_false(mapper):
    for tid in list(mapper._table.index) + ["99999999999"]:
        assert mapper.check_tract(tid).is_opportunity_zone is not False, tid


def test_opportunity_zone_status_three_states(mapper, monkeypatch):
    designated = mapper.check_tract("17031840100")
    assert designated.is_opportunity_zone is True
    assert designated.opportunity_zone_status == "designated"

    not_confirmed = mapper.check_tract("17031010100")
    assert not_confirmed.is_opportunity_zone is None
    assert not_confirmed.opportunity_zone_status == "not-confirmed"

    monkeypatch.setattr("nmtcmapper.mapper.geocode_address", lambda a: None)
    no_tract = mapper.check_address("nowhere at all, XX")
    assert no_tract.opportunity_zone_status == "no-tract"


def test_oz_membership_is_keyed_on_the_set_not_on_tract_found(mapper):
    """THE CARVE-OUT. A GEOID that is designated but absent from the eligibility
    table must still return True — the OZ answer is more complete than the
    eligibility answer there, and a naive "None unless found" rule would destroy
    a correct answer. Driven live against three real retired 2010 GEOIDs in
    test_live_oz_partition_and_carve_out below."""
    m = NMTCMapper.__new__(NMTCMapper)
    m._table = mapper._table.drop(index=["17031840100"])   # designated, now absent
    m._oz_tracts = mapper._oz_tracts
    m.data_source = "test"
    r = m.check_tract("17031840100")
    assert r.tract_found is False
    assert r.is_opportunity_zone is True
    assert r.opportunity_zone_status == "designated"


# ── rendering: the fabrication survives the type change unless killed ────────

def test_summary_of_an_indeterminate_result_says_neither_yes_nor_no(mapper, capsys):
    """§M4.2's grep test. `None` is falsy, so a surviving `'Yes' if x else 'No'`
    would still print `No` after the type was fixed — and the rendered block is
    what a user pastes into a memo. Driven on a tract that is NOT designated, so
    a legitimate `✅ YES` on the carve-out cannot mask a regression."""
    mapper.check_tract("99999999999").summary()
    out = capsys.readouterr().out
    assert ": No" not in out
    assert "Yes" not in out
    assert out.count("❓") >= 3          # eligibility, Non-Metro, High Migration


def test_summary_renders_all_three_opportunity_zone_states(mapper, capsys, monkeypatch):
    mapper.check_tract("17031840100").summary()
    assert "✅ YES — GEOID is on the Dec-2018 designation list" in capsys.readouterr().out

    mapper.check_tract("17031010100").summary()
    out = capsys.readouterr().out
    assert "❓ NOT CONFIRMED — not on the 2018 designation list" in out
    assert "Opportunity Zone: No" not in out

    monkeypatch.setattr("nmtcmapper.mapper.geocode_address", lambda a: None)
    mapper.check_address("nowhere at all, XX").summary()
    assert "❓ UNKNOWN — no census tract resolved" in capsys.readouterr().out


def test_the_true_line_carries_its_qualifier_inline_not_as_a_footer(mapper, capsys):
    """§M4.2: the qualifier is inline for ALL THREE states, including True — 527
    of the 7,356 matched GEOIDs (7.2%) draw under 99% of their land from the
    same-numbered 2010 tract. A footer is what gets dropped when one line is
    pasted into a memo, and the True line is the one most likely to be pasted."""
    mapper.check_tract("17031840100").summary()
    out = capsys.readouterr().out
    oz_block = out.split("Opportunity Zone:")[1].split("High Migration:")[0]
    assert "a claim about the list, not about the parcel" in oz_block


def test_summary_never_uses_a_ternary_on_a_tri_state_field():
    """Structural: the render must be a three-branch switch. A `'Yes' if x else
    'No'` anywhere in summary() is the defect, not a style question."""
    import inspect
    src = inspect.getsource(EligibilityResult.summary)
    assert "if self.is_opportunity_zone else" not in src
    assert "if self.is_non_metro else" not in src
    assert "if self.is_high_migration_rural else" not in src


# ── the two booleans that must STAY plain bool ───────────────────────────────

def test_geocode_success_and_tract_found_stay_bool(mapper):
    """eligibility_status reads both through `not`. Making either tri-state would
    mislabel results; geocode_success in particular means "no unresolved address
    stands between this result and its tract", not "geocoding succeeded"."""
    for r in (mapper.check_tract("17031840100"), mapper.check_tract("99999999999")):
        assert isinstance(r.geocode_success, bool)
        assert isinstance(r.tract_found, bool)


# ── the field drop fails LOUD ────────────────────────────────────────────────

def test_native_area_field_is_gone_and_fails_loudly(mapper):
    r = mapper.check_tract("17031840100")
    with pytest.raises(AttributeError):
        r.is_nmtc_native_area
    with pytest.raises(TypeError):
        EligibilityResult(
            address="x", tract_id="17031840100", nmtc_eligible=True,
            distress_level="lic", poverty_rate=None, ami_ratio=None,
            unemployment_rate=None, is_non_metro=False,
            is_high_migration_rural=False, is_nmtc_native_area=False,
            severe_distress=False, deep_distress=False, geocode_success=True,
        )


def test_enrich_drops_the_native_area_column(mapper, sample_df):
    out = mapper.enrich(sample_df, tract_col="tract_id")
    assert "is_nmtc_native_area" not in out.columns
    with pytest.raises(KeyError):
        out["is_nmtc_native_area"]
    # nine eligibility columns plus eligibility_status
    written = [c for c in out.columns if c not in sample_df.columns]
    assert len(written) == 10
    assert "eligibility_status" in written


def test_summing_opportunity_zone_now_raises(mapper):
    """The loud half of the upgrade table: aggregate arithmetic over the field
    stops silently under-counting and starts raising."""
    results = [mapper.check_tract(t) for t in ("17031840100", "17031010100")]
    with pytest.raises(TypeError):
        sum(r.is_opportunity_zone for r in results)


# ── enrich() carries the tri-state into the frame ────────────────────────────

def test_enrich_absent_row_carries_none_not_false(sample_table):
    df = pd.DataFrame({"tract_id": ["17031840100", "99999999999"]})
    out = enrich_dataframe(df, sample_table, tract_col="tract_id")
    for field in TRACT_DERIVED:
        assert out[field].iloc[1] is None, field
    # the found row is untouched
    assert out["severe_distress"].iloc[0] is not None


def test_the_documented_upgrade_filter_works(sample_table):
    """`~df[col]` on a frame containing indeterminate rows now raises; the
    CHANGELOG tells users to filter with `!= True` instead."""
    df = pd.DataFrame({"tract_id": ["17031840100", "99999999999"]})
    out = enrich_dataframe(df, sample_table, tract_col="tract_id")
    with pytest.raises(TypeError):
        ~out["severe_distress"]
    assert int((out["severe_distress"] != True).sum()) == 1


# ── _compute_eligibility: the three structural defects ───────────────────────

def _one(pr, ami, unemp=0.0, non_metro=False, hmr=False, tid="TEST"):
    return _compute_eligibility(pd.DataFrame([{
        "tract_id": tid, "poverty_rate": pr, "ami_ratio": ami,
        "unemployment_rate": unemp, "is_non_metro": non_metro,
        "is_high_migration_rural": hmr,
    }])).iloc[0]


def test_distress_is_and_ed_with_lic():
    """A tract carried into a distress tier by the unemployment prong alone, with
    poverty under 20% and MFI over 80%, is NOT severe: the Fund's own column-14
    header reads `Severe distress=LIC AND (...)`. On the live file this was the
    whole of the 5,197-row defect — poverty prong 0, MFI prong 0."""
    r = _one(pr=0.05, ami=1.20, unemp=0.30)          # 5.6x national unemployment
    assert r["nmtc_eligible"] == False
    assert r["severe_distress"] == False
    assert r["deep_distress"] == False
    assert r["distress_level"] == "ineligible"


def test_the_missing_conjunct_reached_the_label_too():
    """distress_label tests deep, then severe, and only then nmtc_eligible — so a
    True in either distress column short-circuited before the LIC check was ever
    consulted. AND-ing LIC into the columns repairs the label as a side effect."""
    r = _one(pr=0.05, ami=1.20, unemp=0.30)
    assert r["distress_level"] not in ("severe", "deep")


def test_distress_poverty_prongs_are_strictly_greater():
    """The Fund publishes `Poverty>30%` / `Poverty>40%` (FAQ Q32). At exactly the
    boundary, qualifying on poverty alone, the Fund published NO — 21/21 at 30.0%
    and 13/13 at 40.0%."""
    at_30 = _one(pr=0.30, ami=0.95, unemp=0.01)
    assert at_30["nmtc_eligible"] == True             # >= 0.20, the LIC prong
    assert at_30["severe_distress"] == False          # NOT > 0.30
    just_over = _one(pr=0.3001, ami=0.95, unemp=0.01)
    assert just_over["severe_distress"] == True

    at_40 = _one(pr=0.40, ami=0.95, unemp=0.01)
    assert at_40["deep_distress"] == False            # NOT > 0.40
    assert _one(pr=0.4001, ami=0.95, unemp=0.01)["deep_distress"] == True


def test_lic_poverty_prong_stays_at_least():
    """45D(e)(1)(A) says a poverty rate "of at least 20 percent" — `>=` here is
    correct and must not be reconciled with the distress prongs' `>`."""
    assert _one(pr=0.20, ami=0.95, unemp=0.01)["nmtc_eligible"] == True


def test_the_85_percent_band_needs_both_hmr_and_non_metro():
    """45D(e)(5)(A) attaches the substitution to paragraph (1)(B)(i) — the
    NON-METROPOLITAN branch — and (5)(B) defines "high migration rural county" by
    out-migration alone, with no rurality or metro test. So a metropolitan county
    can meet the definition, and its tracts are governed by (1)(B)(ii), which the
    substitution never touches."""
    band = 0.83                                        # inside (0.80, 0.85]
    assert _one(pr=0.05, ami=band, non_metro=True,  hmr=True)["nmtc_eligible"] == True
    # non-metro alone must NOT widen the band — this was the 932-tract defect
    assert _one(pr=0.05, ami=band, non_metro=True,  hmr=False)["nmtc_eligible"] == False
    # metropolitan HMR: the substitution has nothing to operate on
    assert _one(pr=0.05, ami=band, non_metro=False, hmr=True)["nmtc_eligible"] == False
    # 80% applies to every tract regardless
    assert _one(pr=0.05, ami=0.80, non_metro=False, hmr=False)["nmtc_eligible"] == True


# ── live: the partition the headline rests on ────────────────────────────────

@pytest.mark.live
def test_live_oz_partition_and_carve_out():
    """7,356 True + 78,039 None = 85,395, and `is False` occurs zero times."""
    from nmtcmapper.data.loader import load_opportunity_zones
    table = load_eligibility_table()
    oz = load_opportunity_zones()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = table, oz, "cdfi_fund"

    designated = oz & set(table.index)
    assert len(table) == 85_395
    assert len(designated) == 7_356
    assert len(table) - len(designated) == 78_039

    for tid in list(table.index)[::37]:
        assert m.check_tract(tid).is_opportunity_zone is not False, tid

    # retired 2010 GEOIDs: designated, and absent from the 2020-basis table
    for tid in ("01003011502", "01007010002", "60010950100"):
        r = m.check_tract(tid)
        assert r.is_opportunity_zone is True, tid
        assert r.tract_found is False, tid
        assert r.opportunity_zone_status == "designated", tid


@pytest.mark.live
def test_live_corrected_rule_admits_no_non_lic_distress():
    """The 5,197 → 0 result. Feeding the Fund's own metric columns through the
    corrected rule, no tract reaches a distress tier while not LIC."""
    live = load_eligibility_table()
    out = _compute_eligibility(live[[
        "poverty_rate", "ami_ratio", "unemployment_rate",
        "is_non_metro", "is_high_migration_rural",
    ]].copy())
    lic = live["nmtc_eligible"]
    assert int(((out["severe_distress"] | out["deep_distress"]) & ~lic).sum()) == 0
    assert len(out.loc[~out["nmtc_eligible"]
                       & out["distress_level"].isin(["severe", "deep"])]) == 0
    # the corrected LIC rule reproduces the Fund's published column C exactly
    assert int((out["nmtc_eligible"] != lic).sum()) == 0
    # and the non-metro conjunct is redundant on THIS file, not in logic
    assert int((live["is_high_migration_rural"] & ~live["is_non_metro"]).sum()) == 0


@pytest.mark.live
def test_live_invariants_did_not_move():
    """0.5.0 is a contract release, not a data release."""
    live = load_eligibility_table()
    assert len(live) == 85_395
    assert int(live["nmtc_eligible"].sum()) == 35_335
    assert live["distress_level"].value_counts().to_dict() == {
        "ineligible": 50_060, "lic": 14_153, "severe": 13_121, "deep": 8_061,
    }
    row = live.loc["01013953500"]
    assert bool(row["nmtc_eligible"]) is True
    assert bool(row["is_high_migration_rural"]) is True
    assert row["distress_level"] == "lic"


# ── G1: the fabricated DENOMINATOR in eligible_count() ───────────────────────
#
# Not a fabricated False in a field — a fabricated denominator in a derived
# statistic, on the headline line of the printed summary. Through 0.4.3
# `pct_eligible` was `eligible / total`, which folds every indeterminate row into
# the denominator: the identical fold the comment three lines above it forbids for
# the COUNT. It had no test at all, which is why it survived the 0.4.0 tri-state
# release and the 0.5.0 BUILD-1 audit.

def _counts(mapper, eligible, ineligible, indeterminate):
    """A frame with an exact tri-state mix, straight into eligible_count()."""
    col = [True] * eligible + [False] * ineligible + [None] * indeterminate
    lvl = (["lic"] * eligible + ["ineligible"] * ineligible
           + ["unknown"] * indeterminate)
    return mapper.eligible_count(
        pd.DataFrame({"nmtc_eligible": col, "distress_level": lvl})
    )


def test_pct_is_over_determined_not_over_total(mapper):
    """1 eligible / 1 ineligible / 8 indeterminate. `eligible/total` reported
    10.0% — five times low — where the eligible share of what was actually
    determined is 50.0%."""
    out = _counts(mapper, eligible=1, ineligible=1, indeterminate=8)
    assert out["total"] == 10
    assert out["determined"] == 2
    assert out["indeterminate"] == 8
    assert out["nmtc_eligible"] == 1
    assert out["pct_eligible_of_determined"] == 50.0
    # the old value, and the shape of the fold, must not be recoverable from here
    assert out["pct_eligible_of_determined"] != 10.0


def test_the_old_field_name_is_gone_and_fails_loud(mapper):
    """`pct_eligible` with a changed denominator would be the same silent
    redefinition `is_opportunity_zone` was. Dropping the name makes a caller
    reading the old key raise instead of quietly getting a different number."""
    out = _counts(mapper, eligible=1, ineligible=1, indeterminate=8)
    assert "pct_eligible" not in out
    with pytest.raises(KeyError):
        out["pct_eligible"]


def test_no_determined_rows_gives_None_not_zero_percent(mapper):
    """0.4.3 returned `pct_eligible: 0.0` for an all-indeterminate frame — "0% of
    them are eligible" asserted about an empty set. A rate with no denominator is
    None."""
    out = _counts(mapper, eligible=0, ineligible=0, indeterminate=5)
    assert out["determined"] == 0
    assert out["pct_eligible_of_determined"] is None
    assert out["pct_eligible_of_determined"] is not False   # None, not falsy-0


def test_empty_frame_gives_None_too(mapper):
    out = _counts(mapper, eligible=0, ineligible=0, indeterminate=0)
    assert out["total"] == 0
    assert out["pct_eligible_of_determined"] is None


def test_the_three_states_always_partition_total(mapper):
    for e, i, u in ((3, 2, 5), (0, 7, 0), (4, 0, 0), (1, 1, 8)):
        out = _counts(mapper, e, i, u)
        assert out["nmtc_eligible"] + out["ineligible"] == out["determined"]
        assert out["determined"] + out["indeterminate"] == out["total"]


def test_the_printed_headline_names_its_denominator_inline(mapper, capsys):
    """House standard: the qualifier is inline, never a footer — this is the one
    line a user pastes into a memo, and a bare "(50.0%)" is the fabrication in a
    different font."""
    _counts(mapper, eligible=1, ineligible=1, indeterminate=8)
    out = capsys.readouterr().out
    elig_line = [ln for ln in out.splitlines() if "NMTC Eligible" in ln][0]
    assert "1 of 2 determined" in elig_line
    assert "50.0%" in elig_line
    assert "Determined:" in out
    assert "Indeterminate:" in out


def test_the_zero_denominator_line_states_why_there_is_no_rate(mapper, capsys):
    _counts(mapper, eligible=0, ineligible=0, indeterminate=5)
    out = capsys.readouterr().out
    assert "no rate — nothing was determined" in out
    assert "0.0%" not in out
    assert "(0%)" not in out


def test_eligible_count_never_divides_by_total():
    """Structural, in the spirit of the summary() ternary test: the defect is the
    denominator, so the denominator is what the test pins."""
    import inspect
    src = inspect.getsource(NMTCMapper.eligible_count)
    body = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "eligible / total" not in body
    assert "eligible / determined" in body


# ── G2: the guard written for the wrong null sentinel ────────────────────────
#
# `if self.poverty_rate is not None:` is correct against the None the loader
# emits and a NO-OP against what arrives, because pd.DataFrame(records) coerces
# None -> NaN in a float column and NaN is not None. 1,583 poverty / 2,358 AMI
# FOUND tracts rendered `nan%`. Third instance of the pattern in this portfolio.

def _table_with_null_demographics():
    """A found tract whose demographics are null, built through the SAME
    coercion the live loader goes through — pd.DataFrame() on records carrying
    Python None, not a hand-placed np.nan. If the coercion ever stops happening
    this fixture stops reproducing the defect, which is the correct failure."""
    df = pd.DataFrame([
        {"tract_id": "01003990000", "nmtc_eligible": False,
         "distress_level": "ineligible", "poverty_rate": None,
         "ami_ratio": None, "unemployment_rate": 0.0,
         "is_non_metro": False, "is_high_migration_rural": False,
         "severe_distress": False, "deep_distress": False},
        {"tract_id": "01003990001", "nmtc_eligible": True,
         "distress_level": "lic", "poverty_rate": 0.25,
         "ami_ratio": 0.70, "unemployment_rate": 0.09,
         "is_non_metro": False, "is_high_migration_rural": False,
         "severe_distress": False, "deep_distress": False},
    ]).set_index("tract_id")
    assert df["poverty_rate"].dtype == float          # the coercion happened
    assert df.loc["01003990000", "poverty_rate"] is not None
    assert pd.isna(df.loc["01003990000", "poverty_rate"])
    return df


def test_the_loader_coercion_that_defeats_the_guard_is_real():
    """The premise, asserted rather than assumed: None goes into a float column
    and NaN comes out, and `NaN is not None` is True."""
    t = _table_with_null_demographics()
    v = t.loc["01003990000", "poverty_rate"]
    assert (v is not None) is True        # the old guard's test PASSES on NaN
    assert pd.isna(v) is True             # ...and the value is still missing


def test_found_tract_with_null_demographics_renders_not_available(capsys):
    t = _table_with_null_demographics()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = t, set(), "test"
    r = m.check_tract("01003990000")
    assert r.tract_found is True
    assert r.eligibility_status == "verified-ineligible"
    r.summary()
    out = capsys.readouterr().out
    assert "nan" not in out.lower()
    assert out.count("not available") == 2            # poverty + AMI, not unemployment
    pov = [ln for ln in out.splitlines() if "Poverty Rate" in ln][0]
    assert "not available" in pov
    assert "CDFI Fund published no value" in pov
    # the metric that IS present is unaffected
    assert "Unemployment:     0.0%" in out


def test_the_two_kinds_of_missing_use_two_different_words(capsys):
    """A found tract with no published metric and an indeterminate tract are two
    different states. Rendering both as one word is what made this invisible."""
    t = _table_with_null_demographics()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = t, set(), "test"

    m.check_tract("01003990000").summary()
    found = capsys.readouterr().out
    m.check_tract("99999999999").summary()
    absent = capsys.readouterr().out

    assert "not available" in found and "not available" not in absent
    assert "tract not read" in absent and "tract not read" not in found
    assert "nan" not in found.lower() and "nan" not in absent.lower()


def test_a_real_value_still_renders_as_a_percentage(capsys):
    t = _table_with_null_demographics()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = t, set(), "test"
    m.check_tract("01003990001").summary()
    out = capsys.readouterr().out
    assert "Poverty Rate:     25.0%" in out
    assert "AMI Ratio:        70.0%" in out
    assert "not available" not in out


def test_pct_helper_covers_every_null_sentinel_pandas_can_produce():
    """`pd.isna` rather than a second hand-written check: the lesson of three
    instances of this pattern is that the sentinel is whatever the library that
    touched the column last decided it was."""
    import numpy as np
    from nmtcmapper.eligibility.checker import _pct
    assert _pct(None) == "❓ UNKNOWN — tract not read"
    for null in (float("nan"), np.nan, np.float64("nan"), pd.NA, pd.NaT):
        assert _pct(null).startswith("not available"), repr(null)
    assert _pct(0.0) == "0.0%"
    assert _pct(0.197) == "19.7%"
    assert _pct(1.0) == "100.0%"


def test_summary_no_longer_guards_the_metrics_on_is_not_None():
    """Structural: the wrong-sentinel guard must not come back."""
    import inspect
    src = inspect.getsource(EligibilityResult.summary)
    for field in ("poverty_rate", "ami_ratio", "unemployment_rate"):
        assert f"self.{field} is not None" not in src, field


def test_the_metric_lines_are_never_silently_omitted(capsys):
    """Omitting the line was a THIRD rendering of missing, indistinguishable from
    "nobody looked". All three lines print on every path."""
    t = _table_with_null_demographics()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = t, set(), "test"
    for tid in ("01003990000", "01003990001", "99999999999"):
        m.check_tract(tid).summary()
        out = capsys.readouterr().out
        for label in ("Poverty Rate:", "AMI Ratio:", "Unemployment:"):
            assert label in out, (tid, label)


def test_empty_batch_has_no_match_rate(capsys):
    """Found by the G1 denominator sweep, fixed with G2's rendering family:
    `matched/total` on an empty batch is a numpy scalar divide, so it returned
    nan rather than raising, and printed "nan% match rate"."""
    from nmtcmapper.geocoder.census import geocode_batch
    out_df = geocode_batch(pd.DataFrame({"address": []}), address_col="address")
    out = capsys.readouterr().out
    assert len(out_df) == 0
    assert "nan" not in out.lower()
    assert "no match rate — the batch was empty" in out


# ── G3: the bool() wrapper on check_tract()'s found path is load-bearing ─────
#
# G2's `is not None` sweep found twelve guards, of which FOUR are correct only
# because check_tract() coerces the field with bool() before the guard ever sees
# it:
#
#   1. _tri(self.is_non_metro)              — summary()
#   2. _tri(self.is_high_migration_rural)   — summary()
#   3. self.nmtc_eligible is None           — eligibility_status
#   4. self.nmtc_eligible is None           — summary()
#
# All four test `is None`. Strip the wrapper and a NaN reaches them intact: NaN
# is not None, so the guard is skipped, and NaN is TRUTHY, so _tri returns "Yes".
# That is a fabricated POSITIVE — strictly worse than the fabricated negative
# this release exists to remove, because a false "eligible" closes a deal that
# does not qualify.
#
# Unreachable today: all four source columns are dtype=bool on the live file with
# no possible NaN. But nothing else in the suite would catch the wrapper's
# removal, which is exactly the shape of defect that survived four releases here.
# Structural, in the spirit of test_eligible_count_never_divides_by_total.

BOOL_WRAPPED_ON_THE_FOUND_PATH = (
    "nmtc_eligible", "is_non_metro", "is_high_migration_rural",
    "severe_distress", "deep_distress",
)


def test_the_found_path_coerces_every_tri_state_field_with_bool():
    """Pin the wrapper itself. The four `is None` guards downstream cannot
    distinguish NaN from a real value, so the coercion is what makes them
    correct — and it is invisible at every one of those four call sites."""
    import inspect
    import re
    from nmtcmapper.eligibility.checker import _tri

    # The failure mode this pins, demonstrated rather than asserted: an unwrapped
    # NaN slips both halves of every one of the four downstream guards.
    nan = float("nan")
    assert nan is not None                 # the `is None` guard does not fire
    assert bool(nan) is True               # ...and NaN is truthy
    assert _tri(nan) == "Yes"              # so it renders as a fabricated positive
    assert _tri(bool(nan)) == "Yes"        # which the wrapper cannot itself repair
    assert _tri(None) == "❓ UNKNOWN — tract not read"

    src = inspect.getsource(check_tract)
    body = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    for field in BOOL_WRAPPED_ON_THE_FOUND_PATH:
        assert re.search(rf'"{field}":\s*bool\(row\.get\(', body), (
            f"check_tract()'s found path no longer wraps {field!r} in bool(). "
            f"A NaN in that column now reaches summary()/eligibility_status "
            f"intact, where `is None` misses it and truthiness renders it 'Yes'."
        )


# ── live: G1 and G2 against the real 85,395-row file ─────────────────────────

@pytest.mark.live
def test_live_no_found_tract_renders_nan(capsys):
    """1,583 poverty + 2,358 AMI null cells on the live file, and zero of them
    may reach a rendered summary as `nan%`. Driven over every found tract that
    has a null metric, not a sample of them."""
    table = load_eligibility_table()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = table, set(), "cdfi_fund"

    null_pov = table.index[table["poverty_rate"].isna()]
    null_ami = table.index[table["ami_ratio"].isna()]
    assert len(null_pov) == 1_583
    assert len(null_ami) == 2_358

    for tid in set(null_pov) | set(null_ami):
        r = m.check_tract(tid)
        assert r.tract_found is True          # FOUND tracts, not indeterminate
        r.summary()
        out = capsys.readouterr().out
        assert "nan" not in out.lower(), tid
        assert "not available" in out, tid
        assert "tract not read" not in out, tid


@pytest.mark.live
def test_live_pct_of_determined_on_a_real_mixed_frame(capsys):
    """The 1/1/8 shape with real GEOIDs: two rows in the live table with opposite
    verdicts, eight absent."""
    table = load_eligibility_table()
    m = NMTCMapper.__new__(NMTCMapper)
    m._table, m._oz_tracts, m.data_source = table, set(), "cdfi_fund"

    eligible_tid = table.index[table["nmtc_eligible"]][0]
    ineligible_tid = table.index[~table["nmtc_eligible"]][0]
    absent = [f"9999999999{i}" for i in range(8)]
    df = pd.DataFrame({"tract_id": [eligible_tid, ineligible_tid] + absent})
    out = m.eligible_count(enrich_dataframe(df, table, tract_col="tract_id"))

    assert out["total"] == 10
    assert out["determined"] == 2
    assert out["indeterminate"] == 8
    assert out["pct_eligible_of_determined"] == 50.0
    assert "pct_eligible" not in out
