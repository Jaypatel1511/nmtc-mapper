"""Fix 4 — summary() and enrich() surface the tri-state; truthiness sweep.

- EligibilityResult.summary() must render an indeterminate result distinctly and
  NEVER print "❌ NO" for it (the inline-qualifier house standard).
- enrich_dataframe adds an additive ``eligibility_status`` column distinguishing
  verified-eligible / verified-ineligible / not-found / geocode-failed.
- eligible_count must not treat a None (indeterminate) verdict as an ineligible
  one — the None-as-falsy aggregate fabrication.
"""
import numpy as np
import pandas as pd
import pytest

from nmtcmapper.eligibility.checker import (
    EligibilityResult, check_tract, enrich_dataframe,
)


def _result(**over):
    base = dict(
        address="x", tract_id="17031030604", nmtc_eligible=False,
        distress_level="ineligible", poverty_rate=0.197, ami_ratio=0.9127,
        unemployment_rate=0.017, is_non_metro=False, is_high_migration_rural=False,
        is_nmtc_native_area=False, severe_distress=False, deep_distress=False,
        geocode_success=True, is_opportunity_zone=False, tract_found=True,
    )
    base.update(over)
    return EligibilityResult(**base)


# ── summary() renders the unknown state distinctly ────────────────────────────

def test_summary_indeterminate_not_rendered_as_no(capsys):
    r = _result(nmtc_eligible=None, distress_level="unknown",
                tract_found=False, geocode_success=False,
                poverty_rate=None, ami_ratio=None, unemployment_rate=None)
    r.summary()
    out = capsys.readouterr().out
    assert "❌ NO" not in out                 # the exact fabrication to avoid
    assert "UNKNOWN" in out.upper()
    # the qualifier is inline on the NMTC Eligible line, not a footer
    elig_line = [ln for ln in out.splitlines() if "NMTC Eligible" in ln][0]
    assert "UNKNOWN" in elig_line.upper()
    assert "indeterminate" in elig_line.lower()


def test_summary_verified_ineligible_still_says_no(capsys):
    _result(nmtc_eligible=False, distress_level="ineligible").summary()
    out = capsys.readouterr().out
    assert "❌ NO" in out


def test_summary_eligible_says_yes(capsys):
    _result(nmtc_eligible=True, distress_level="lic").summary()
    out = capsys.readouterr().out
    assert "✅ YES" in out


# ── eligibility_status four-way ───────────────────────────────────────────────

def test_eligibility_status_four_way():
    assert _result(nmtc_eligible=True, distress_level="lic").eligibility_status == "verified-eligible"
    assert _result(nmtc_eligible=False).eligibility_status == "verified-ineligible"
    assert _result(nmtc_eligible=None, tract_found=False,
                   geocode_success=True).eligibility_status == "not-found"
    assert _result(nmtc_eligible=None, tract_found=False,
                   geocode_success=False).eligibility_status == "geocode-failed"


# ── enrich_dataframe eligibility_status column ────────────────────────────────

def test_enrich_adds_eligibility_status_column(sample_table):
    df = pd.DataFrame({"tract_id": [
        "17031840100",   # eligible
        "17031010100",   # in table, ineligible
        "99999999999",   # syntactically valid, absent -> not-found
        np.nan,          # no tract resolved -> geocode-failed
    ]})
    out = enrich_dataframe(df, sample_table, tract_col="tract_id")
    assert "eligibility_status" in out.columns
    assert list(out["eligibility_status"]) == [
        "verified-eligible", "verified-ineligible", "not-found", "geocode-failed",
    ]


def test_enrich_absent_tract_is_none_not_false(sample_table):
    df = pd.DataFrame({"tract_id": ["99999999999"]})
    out = enrich_dataframe(df, sample_table, tract_col="tract_id")
    # tri-state carried into the frame: absent -> None + "unknown", never False.
    assert out["nmtc_eligible"].iloc[0] is None
    assert out["distress_level"].iloc[0] == "unknown"


def test_enrich_preserves_existing_columns(sample_table):
    df = pd.DataFrame({"project": ["A"], "tract_id": ["17031840100"]})
    out = enrich_dataframe(df, sample_table, tract_col="tract_id")
    assert "project" in out.columns            # additive; nothing removed/renamed
    assert "nmtc_eligible" in out.columns


# ── eligible_count truthiness sweep ───────────────────────────────────────────

def test_eligible_count_does_not_count_unknown_as_ineligible(mapper):
    df = pd.DataFrame({"tract_id": [
        "17031840100",   # eligible
        "17031010100",   # verified ineligible
        "99999999999",   # indeterminate (None)
    ]})
    enriched = mapper.enrich(df, tract_col="tract_id")
    summary = mapper.eligible_count(enriched)
    # The indeterminate row must NOT inflate the ineligible tally (None-as-falsy bug).
    assert summary["ineligible"] == 1
    assert summary.get("indeterminate") == 1
    assert summary["total"] == 3
    assert summary["nmtc_eligible"] == 1
