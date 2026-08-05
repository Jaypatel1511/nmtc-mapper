"""@live smoke tests — download and parse the REAL CDFI Fund eligibility file.

0.4.2 exists because the CDFI Fund re-published this file IN PLACE, at the same
URL, with two renamed headers; every live load raised EligibilitySchemaError.
The offline suite mocks pyxlsb, so it can only prove the loader agrees with a
fixture WE wrote — it structurally cannot catch the next in-place re-publish.
Only this module consumes the artifact it certifies.

Network-bound and deselected in CI (`-m "not live"`). Run locally with:

    pytest tests/test_live_eligibility_file.py -m live -v

Not skip-marked: these run whenever `live` is selected, and never otherwise.
"""
import pytest

from nmtcmapper.data.loader import load_eligibility_table
from nmtcmapper.data.schema import (
    ELIGIBILITY_XLSB_EXPECTED_HEADERS,
    DEEP_POVERTY_THRESHOLD, DEEP_AMI_THRESHOLD, DEEP_UNEMPLOYMENT_MULTIPLIER,
    SEVERE_POVERTY_THRESHOLD, SEVERE_AMI_THRESHOLD,
    SEVERE_UNEMPLOYMENT_MULTIPLIER,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_table():
    """The real table, downloaded (or read from the user cache) once."""
    return load_eligibility_table()


def test_live_file_loads_and_has_the_full_universe(live_table):
    """The headline 0.4.2 assertion: the pinned headers match the live file, so
    _validate_xlsb_header does not raise and every row parses."""
    assert len(live_table) == 85_395


def test_live_eligible_count_reflects_the_widened_column_c(live_table):
    """July 2026 widened column C to carry High Migration Rural tracts, taking
    the eligible count from 35,167 to 35,335 (+168). If this reads 35,167 the
    Fund has reverted the widening and the CHANGELOG note for 0.4.2 is stale."""
    assert int(live_table["nmtc_eligible"].sum()) == 35_335


def test_live_high_migration_rural_tracts_are_all_lic(live_table):
    """The semantic content of the widening: all 1,422 High Migration Rural
    tracts are now flagged eligible in column C. Under Aug-2025b, 168 of them
    were not — nmtc-mapper 0.4.1 reported those as NOT NMTC eligible, which
    contradicted 26 USC 45D(e)(2) as implemented by AJCA 2004 sec. 223."""
    hmr = live_table[live_table["is_high_migration_rural"]]
    assert len(hmr) == 1_422
    assert bool(hmr["nmtc_eligible"].all())


def test_live_severe_and_deep_flags_match_the_corrected_thresholds(live_table):
    """Recompute the published distress flags from the published metrics using
    the 0.4.2 constants. The CDFI Fund did NOT recompute columns O/P after
    widening column C, so exactly 20 severe / 3 deep rows disagree — all of them
    newly-LIC High Migration Rural tracts. Anything beyond that means our
    thresholds have drifted from the Fund's definition again.

    Bounding the disagreement is the point: the 0.4.1 constants (MFI<=50%,
    unemployment>=2.0x) disagree on 5,025 rows, which this assertion catches.
    """
    df = live_table
    ratio = df["unemployment_rate"] / 0.054      # tract rate / national rate

    severe = df["nmtc_eligible"] & (
        (df["poverty_rate"] > SEVERE_POVERTY_THRESHOLD)
        | (df["ami_ratio"] <= SEVERE_AMI_THRESHOLD)
        | (ratio >= SEVERE_UNEMPLOYMENT_MULTIPLIER)
    )
    deep = df["nmtc_eligible"] & (
        (df["poverty_rate"] > DEEP_POVERTY_THRESHOLD)
        | (df["ami_ratio"] <= DEEP_AMI_THRESHOLD)
        | (ratio >= DEEP_UNEMPLOYMENT_MULTIPLIER)
    )

    assert int((severe != df["severe_distress"]).sum()) == 20
    assert int((deep != df["deep_distress"]).sum()) == 3


def test_live_headers_are_byte_identical_to_the_pins():
    """Read the live header row directly and compare every pinned index. This is
    the check that failed in the field and the one that will fail next time."""
    import pyxlsb
    from nmtcmapper.data.loader import _normalize_header, download_eligibility_file
    from nmtcmapper.data.schema import ELIGIBILITY_XLSB_SHEET

    path = download_eligibility_file()
    with pyxlsb.open_workbook(str(path)) as wb:
        with wb.get_sheet(ELIGIBILITY_XLSB_SHEET) as sheet:
            header = [c.v for c in next(iter(sheet.rows()))]

    assert len(header) == 16
    for idx, expected in ELIGIBILITY_XLSB_EXPECTED_HEADERS.items():
        assert _normalize_header(header[idx]) == _normalize_header(expected), idx
