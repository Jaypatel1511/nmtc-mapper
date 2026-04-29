import pytest
import pandas as pd
from nmtcmapper.data.loader import _build_sample_table, _compute_eligibility


def test_sample_table_returns_dataframe():
    df = _build_sample_table()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_sample_table_has_required_columns():
    df = _build_sample_table()
    required = ["nmtc_eligible", "distress_level", "poverty_rate", "ami_ratio"]
    for col in required:
        assert col in df.columns


def test_sample_table_has_eligible_tracts():
    df = _build_sample_table()
    assert df["nmtc_eligible"].any()


def test_sample_table_has_ineligible_tracts():
    df = _build_sample_table()
    assert (~df["nmtc_eligible"]).any()


def test_distress_levels_valid():
    df = _build_sample_table()
    valid = {"deep", "severe", "lic", "ineligible"}
    assert set(df["distress_level"].unique()).issubset(valid)


def test_high_poverty_is_eligible():
    df = pd.DataFrame([{
        "tract_id": "TEST001",
        "poverty_rate": 0.35,
        "ami_ratio": 0.90,
        "unemployment_rate": 0.05,
        "is_non_metro": False,
        "is_high_migration_rural": False,
    }])
    result = _compute_eligibility(df)
    assert result["nmtc_eligible"].iloc[0] == True


def test_low_ami_is_eligible():
    df = pd.DataFrame([{
        "tract_id": "TEST002",
        "poverty_rate": 0.10,
        "ami_ratio": 0.75,
        "unemployment_rate": 0.04,
        "is_non_metro": False,
        "is_high_migration_rural": False,
    }])
    result = _compute_eligibility(df)
    assert result["nmtc_eligible"].iloc[0] == True


def test_affluent_tract_not_eligible():
    df = pd.DataFrame([{
        "tract_id": "TEST003",
        "poverty_rate": 0.05,
        "ami_ratio": 1.20,
        "unemployment_rate": 0.02,
        "is_non_metro": False,
        "is_high_migration_rural": False,
    }])
    result = _compute_eligibility(df)
    assert result["nmtc_eligible"].iloc[0] == False


def test_deep_distress_classified():
    df = pd.DataFrame([{
        "tract_id": "TEST004",
        "poverty_rate": 0.45,
        "ami_ratio": 0.45,
        "unemployment_rate": 0.15,
        "is_non_metro": False,
        "is_high_migration_rural": False,
    }])
    result = _compute_eligibility(df)
    assert result["distress_level"].iloc[0] == "deep"
