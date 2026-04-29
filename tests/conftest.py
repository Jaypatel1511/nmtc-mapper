import pytest
import pandas as pd
from nmtcmapper.data.loader import _build_sample_table
from nmtcmapper.mapper import NMTCMapper


@pytest.fixture
def sample_table():
    return _build_sample_table()


@pytest.fixture
def mapper(monkeypatch):
    """NMTCMapper with sample data — no real download."""
    monkeypatch.setattr(
        "nmtcmapper.data.loader.download_eligibility_file",
        lambda force=False: None
    )
    return NMTCMapper()


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "project_name": [
            "Southside Health Center",
            "North Shore Office",
            "Detroit Manufacturing",
            "NYC Bronx Project",
        ],
        "tract_id": [
            "17031840100",  # Chicago South Side — eligible
            "17031010100",  # Chicago North Shore — not eligible
            "26163518300",  # Detroit — eligible
            "36061015900",  # NYC Bronx — eligible
        ]
    })
