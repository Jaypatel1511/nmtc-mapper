import pytest
import pandas as pd
from nmtcmapper.data.loader import load_sample_table
from nmtcmapper.mapper import NMTCMapper


@pytest.fixture
def sample_table():
    return load_sample_table()


@pytest.fixture
def mapper():
    """NMTCMapper on the sanctioned offline sample data — zero network.

    Previously this monkeypatched download_eligibility_file to return None, which
    only produced a working mapper *because* of the silent sample-fallback bug
    fixed in 0.3.4. Now it uses the explicit from_sample() constructor.
    """
    return NMTCMapper.from_sample()


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
