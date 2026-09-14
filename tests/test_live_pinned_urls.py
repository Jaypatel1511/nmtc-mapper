"""@live gates — every externally-pinned URL in this package must answer 200.

THE GATE THAT WOULD HAVE CAUGHT THIS EIGHT DAYS BEFORE 0.6.0 SHIPPED. On 2026-09-03
the CDFI Fund replaced the eligibility workbook at a new URL and the pinned one
began returning 403. Every warm cache kept serving the old bytes, so nothing on
any developer machine noticed; a cold install got no NMTC answer at all. 0.4.3,
0.5.0 and 0.6.0 all pin the same dead literal, so "downgrade" was not a
workaround. The package failed safe (EligibilityDownloadError, no fabricated
verdict), which is why this was an availability defect and not a correctness
one — but nothing turned the silent break into a loud one.

RULE: a pinned URL to a third party is a dependency with no version constraint
and no notification. The only thing that makes its disappearance loud is a
gate that fetches it. These are `@live`, so CI deselects them (`-m "not live"`)
— which is exactly why they are named in CONTRIBUTING.md's pre-tag checklist.
A live gate nobody runs is the gate nobody ran.

Each failure names where to look for the replacement, because the person who
sees it is the person who has to find the new file.

Run locally with:

    pytest tests/test_live_pinned_urls.py -m live -v

Not skip-marked: these run whenever `live` is selected, and never otherwise.
"""
import io

import pytest
import requests

from nmtcmapper.data.schema import (
    CDFI_FUND_LIC_URL_2020, OZ_URL_2018, OZ2_URL,
    CENSUS_GEOCODER_URL, CENSUS_GEOCODER_BATCH_URL,
    TRACT_VINTAGE,
)

pytestmark = pytest.mark.live

# Where a human finds the replacement when the pinned URL dies. The CDFI Fund
# page is the one that listed the September-2026 file; the others are the
# publishers' landing pages for the respective datasets/services.
CDFI_GEOGRAPHIC_REPORTS = "https://www.cdfifund.gov/documents/geographic-reports"
CDFI_OPPORTUNITY_ZONES = "https://www.cdfifund.gov/opportunity-zones"
TREASURY_TAX_POLICY = "https://home.treasury.gov/policy-issues/tax-policy"
CENSUS_GEOCODER_HOME = "https://geocoding.geo.census.gov/geocoder/"

# A browser-shaped UA. cdfifund.gov's origin serves the same status either way
# (re-verified 2026-09-13: the dead URL is 403 to curl's default UA AND to a
# browser UA; the live one is 200 to both), so this is not what makes the gate
# pass — it is so the gate requests the file the way a user's browser does.
_HEADERS = {"User-Agent": "nmtc-mapper live-url gate (+https://github.com/Jaypatel1511/nmtc-mapper)"}


def assert_url_is_live(name: str, url: str, where_to_look: str, *,
                       method: str = "GET", **request_kwargs) -> requests.Response:
    """Request `url` the way the package does and fail on ANY non-200.

    The failure text names the constant, the status, and the page where the
    replacement is to be found. A redirect is followed (the Fund's `?file=` URLs
    are Drupal file routes) — what is asserted is the FINAL status."""
    try:
        resp = requests.request(method, url, headers=_HEADERS, timeout=60,
                                stream=True, allow_redirects=True, **request_kwargs)
    except requests.exceptions.RequestException as e:
        pytest.fail(
            f"{name} is unreachable: {type(e).__name__}: {e}\n"
            f"  url: {url}\n"
            f"  If the host is up, the file may have moved — look at "
            f"{where_to_look}"
        )
    try:
        assert resp.status_code == 200, (
            f"{name} returned HTTP {resp.status_code}, not 200.\n"
            f"  pinned : {url}\n"
            f"  final  : {resp.url}\n"
            f"  The publisher has moved or withdrawn this file. Find the "
            f"replacement at {where_to_look} and re-pin the constant — "
            f"do NOT downgrade: every earlier release pins the same literal."
        )
    finally:
        resp.close()
    return resp


# ── The four data files ──────────────────────────────────────────────────────

def test_live_cdfi_fund_eligibility_url_answers_200():
    """The 0.6.1 outage, as a gate. The Fund lists this file under
    'New Markets Tax Credit 2016-2020 ACS Low-Income Communities and Distress'
    on the geographic-reports page; when this fails, that is where the new
    link is."""
    resp = assert_url_is_live("CDFI_FUND_LIC_URL_2020", CDFI_FUND_LIC_URL_2020,
                              CDFI_GEOGRAPHIC_REPORTS)
    ctype = resp.headers.get("Content-Type", "")
    assert "spreadsheetml" in ctype or "octet-stream" in ctype or "excel" in ctype, (
        f"CDFI_FUND_LIC_URL_2020 answered 200 but with Content-Type {ctype!r} — "
        f"an HTML page at a 200 is the maintenance-page failure mode the "
        f"download guard exists for. Check {CDFI_GEOGRAPHIC_REPORTS}."
    )


def test_live_oz_2018_designation_url_answers_200():
    assert_url_is_live("OZ_URL_2018", OZ_URL_2018, CDFI_OPPORTUNITY_ZONES)


def test_live_treasury_oz2_url_answers_200():
    """The digest gate in test_live_oz2_file.py reports a RE-PUBLISH; this one
    reports a DISAPPEARANCE, which the digest gate would only surface as a
    download error deep in a fixture."""
    assert_url_is_live("OZ2_URL", OZ2_URL, TREASURY_TAX_POLICY)


# ── The two geocoder endpoints, requested the way the package requests them ──

def test_live_census_geocoder_single_endpoint_answers_200():
    """Bare GET on the endpoint is a 200 HTML form page, which proves only that
    the host is up. Send the request the package sends — a real address under
    the shipped benchmark/vintage — so the gate covers the endpoint AND the
    pinned vintage names."""
    assert_url_is_live(
        "CENSUS_GEOCODER_URL", CENSUS_GEOCODER_URL, CENSUS_GEOCODER_HOME,
        params={
            "street": "5701 N Sheridan Rd", "city": "Chicago", "state": "IL",
            "zip": "60660", "format": "json",
            "benchmark": TRACT_VINTAGE.geocoder_benchmark,
            "vintage": TRACT_VINTAGE.geocoder_vintage,
        },
    )


def test_live_census_geocoder_batch_endpoint_answers_200():
    """The batch endpoint is POST-only (a GET is a 400 by design, verified
    2026-09-13), so the gate posts a one-row batch."""
    assert_url_is_live(
        "CENSUS_GEOCODER_BATCH_URL", CENSUS_GEOCODER_BATCH_URL, CENSUS_GEOCODER_HOME,
        method="POST",
        files={"addressFile": ("batch.csv",
                               io.BytesIO(b"1,5701 N Sheridan Rd,Chicago,IL,60660\n"),
                               "text/csv")},
        data={"benchmark": TRACT_VINTAGE.geocoder_benchmark,
              "vintage": TRACT_VINTAGE.geocoder_vintage},
    )


# ── Red proof: the gate can fail, and says the right thing when it does ──────

def test_live_gate_fails_loudly_on_a_dead_url():
    """A gate that cannot fail is a false assurance. Point the helper at a path
    under the Fund's own host that is known to 404 and assert the failure
    names the status and the page to look at. (The 0.6.0 pin itself —
    `?file=2025-08/NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb` — is
    a 403 today and would serve the same purpose, but the Fund could restore
    it; a path that never existed cannot come back.)"""
    dead = CDFI_GEOGRAPHIC_REPORTS + "/this-path-has-never-existed-0.6.1"
    with pytest.raises(AssertionError) as ei:
        assert_url_is_live("DEAD_URL", dead, CDFI_GEOGRAPHIC_REPORTS)
    msg = str(ei.value)
    assert "DEAD_URL returned HTTP 404" in msg
    assert CDFI_GEOGRAPHIC_REPORTS in msg
    assert "do NOT downgrade" in msg
