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
