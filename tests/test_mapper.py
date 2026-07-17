import pytest
import pandas as pd
from nmtcmapper.eligibility.checker import EligibilityResult


def test_mapper_loads(mapper):
    assert mapper.tract_count > 0


def test_mapper_eligible_tracts(mapper):
    assert mapper.eligible_tract_count > 0


def test_check_tract_eligible(mapper):
    result = mapper.check_tract("17031840100")
    assert isinstance(result, EligibilityResult)
    assert result.nmtc_eligible == True
    assert result.tract_id == "17031840100"


def test_check_tract_ineligible(mapper):
    result = mapper.check_tract("17031010100")
    assert result.nmtc_eligible == False


def test_check_tract_unknown(mapper):
    # 0.4.0 tri-state: an absent tract is INDETERMINATE, not "ineligible".
    result = mapper.check_tract("99999999999")
    assert result.nmtc_eligible is None
    assert result.distress_level == "unknown"
    assert result.tract_found is False


def test_enrich_with_tract_col(mapper, sample_df):
    result = mapper.enrich(sample_df, tract_col="tract_id")
    assert "nmtc_eligible" in result.columns
    assert "distress_level" in result.columns
    assert len(result) == len(sample_df)


def test_eligible_count_summary(mapper, sample_df):
    enriched = mapper.enrich(sample_df, tract_col="tract_id")
    summary = mapper.eligible_count(enriched)
    assert "total" in summary
    assert "nmtc_eligible" in summary
    assert summary["total"] == len(sample_df)


def test_result_summary_runs(mapper):
    result = mapper.check_tract("17031840100")
    result.summary()


def test_eligible_count_raises_without_enrich(mapper, sample_df):
    with pytest.raises(ValueError, match="Run .enrich()"):
        mapper.eligible_count(sample_df)


def test_oz_tract_count_positive(mapper):
    assert mapper.oz_tract_count > 0


def test_check_tract_has_oz_flag(mapper):
    result = mapper.check_tract("17031840100")
    assert hasattr(result, "is_opportunity_zone")
    assert isinstance(result.is_opportunity_zone, bool)
