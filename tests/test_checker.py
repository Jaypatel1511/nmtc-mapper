import pytest
import pandas as pd
from nmtcmapper.eligibility.checker import check_tract, enrich_dataframe


def test_check_known_eligible_tract(sample_table):
    result = check_tract("17031840100", sample_table)
    assert result["nmtc_eligible"] == True


def test_check_known_ineligible_tract(sample_table):
    result = check_tract("17031010100", sample_table)
    assert result["nmtc_eligible"] == False


def test_check_unknown_tract(sample_table):
    # 0.4.0 tri-state: an absent tract is INDETERMINATE, not "ineligible".
    result = check_tract("99999999999", sample_table)
    assert result["nmtc_eligible"] is None
    assert result["distress_level"] == "unknown"
    assert result["tract_found"] is False


def test_enrich_dataframe(sample_table, sample_df):
    result = enrich_dataframe(sample_df, sample_table, tract_col="tract_id")
    assert "nmtc_eligible" in result.columns
    assert "distress_level" in result.columns
    assert len(result) == len(sample_df)


def test_enrich_eligible_count(sample_table, sample_df):
    result = enrich_dataframe(sample_df, sample_table, tract_col="tract_id")
    assert result["nmtc_eligible"].sum() >= 2


def test_distress_levels_present(sample_table, sample_df):
    result = enrich_dataframe(sample_df, sample_table, tract_col="tract_id")
    assert result["distress_level"].notna().all()
