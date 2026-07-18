"""@live smoke tests — hit the REAL Census geocoder under the shipped default.

These prove, end-to-end against the live endpoint, that the 0.4.1 default
(vintage=Census2020_Current, benchmark=Public_AR_Current) resolves the pinned
addresses onto the 2020 tract geography the eligibility table carries.

Network-bound and deselected in CI (`-m "not live"`). Run locally with:

    pytest tests/test_live_geocoder.py -m live -v

Not skip-marked: these run whenever `live` is selected, and never otherwise.
"""
import pytest

from nmtcmapper.geocoder.census import geocode_address

pytestmark = pytest.mark.live


def test_live_hartford_resolves_to_legacy_county_2020_tract():
    # The bug case: on 0.4.0 (Current_Current) this returned COG tract
    # 09110524600 (absent from the table -> not-found). Under Census2020_Current
    # it returns the legacy-county tract the CDFI Fund table keys on.
    assert geocode_address("765 Asylum Ave, Hartford, CT 06105") == "09003524600"


def test_live_seattle_resolves_to_2020_tract_not_2010():
    # ...007101 is the 2020 tract; ...007100 is the 2010 tract it split from.
    assert geocode_address("400 Broad St, Seattle, WA 98109") == "53033007101"


def test_live_chicago_control_unchanged():
    assert geocode_address("5701 N Sheridan Rd, Chicago, IL 60660") == "17031030604"
