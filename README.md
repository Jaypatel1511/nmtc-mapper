# nmtc-mapper 🗺️

**Automated NMTC eligibility checker for addresses and census tracts.**

Pass a DataFrame of addresses and get back a **tri-state** `nmtc_eligible` column
(`True` / `False` / `None`), distress level, poverty rate, AMI ratio, and more —
using official CDFI Fund and Census Bureau data. No manual lookups required.

`nmtc_eligible` is `Optional[bool]`: `True` (verified eligible), `False`
(verified ineligible — the CDFI Fund file explicitly says NO), or `None`
(**indeterminate** — the address could not be geocoded, or the tract is absent
from the ~85k-tract universe). `None` is **not** a falsy "ineligible": treating
it as `False` fabricates a verified-ineligible answer. The additive
`eligibility_status` column names the four outcomes explicitly —
`verified-eligible` / `verified-ineligible` / `not-found` / `geocode-failed`.

---

## Why nmtc-mapper?

The CDFI Fund provides a manual web tool (CIMS) for checking NMTC eligibility
one address at a time. nmtc-mapper automates this — pass 10,000 addresses and
get results in seconds, using the same official data source.

---

## Installation

    # docs-check: skip shell installation command, not executable Python
    pip install nmtc-mapper

---

## Quickstart

    # docs-check: skip NMTCMapper() downloads the multi-MB CDFI Fund file and check_address hits the live Census geocoder
    from nmtcmapper import NMTCMapper

    mapper = NMTCMapper()

    # Single address (geocodes automatically)
    result = mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")
    result.summary()
    print(result.nmtc_eligible)      # True / False / None (None = indeterminate)
    print(result.eligibility_status) # "verified-eligible" | "verified-ineligible"
                                     #  | "not-found" | "geocode-failed"
    print(result.distress_level)     # "deep" / "severe" / "lic" / "ineligible" / "unknown"
    print(result.poverty_rate)       # 0.38  (None if the tract is indeterminate)

    # Known census tract (no geocoding needed)
    result = mapper.check_tract("17031840100")
    print(result.nmtc_eligible)    # True

    # Batch — enrich a DataFrame of addresses
    import pandas as pd
    df = pd.read_csv("projects.csv")   # must have 'address' column
    df = mapper.enrich(df, address_col="address")
    print(df["nmtc_eligible"].value_counts())
    print(df["distress_level"].value_counts())

    # If you already have census tract IDs
    df = mapper.enrich(df, tract_col="tract_id")

    # Summary stats
    mapper.eligible_count(df)

---

## Failure behavior & offline / demo mode

`NMTCMapper()` downloads the official CDFI Fund eligibility and Opportunity Zone
files (cached under `~/.nmtcmapper/cache`). As of **0.3.4** it **fails loud**: if
a download or parse fails, it raises a typed error instead of silently
substituting demo data. (Before 0.3.4 any failure silently fell back to a
12-tract synthetic sample, which could report a real, eligible tract as
"ineligible" — see the CHANGELOG.)

    # docs-check: skip constructs NMTCMapper(), which downloads the CDFI Fund file
    from nmtcmapper import NMTCMapper, NMTCMapperError

    try:
        mapper = NMTCMapper()
    except NMTCMapperError as e:
        # Blocked network, moved URL, corrupt file, etc. — never a fabricated answer.
        print(f"Could not load real NMTC data: {e}")
        raise

The exception hierarchy (`NMTCMapperError` → `EligibilityDataError` /
`OZDataError` → specific `*DownloadError` / `*ParseError` leaves) is exported
from the top level, so you can catch broadly or precisely.

**Explicit demo / offline data** — for examples, tests, or an air-gapped demo,
opt in to the synthetic sample dataset. This performs **no network calls** and
stamps the mapper so you can tell demo answers from real ones:

    # docs-check: run sample-mode
    from nmtcmapper import NMTCMapper, load_sample_table

    mapper = NMTCMapper.from_sample()   # 12 sample tracts + 6 OZ tracts, offline
    print(mapper.data_source)           # "sample"   (real data → "cdfi_fund")

    df = load_sample_table()            # the raw 12-tract sample frame

> ⚠️ Sample data is 12 synthetic-vintage tracts for demos and tests. It is
> **never** valid for a real NMTC eligibility answer.

---

## Eligibility Rules (2016-2020 ACS — mandatory since Sept 1, 2024)

A census tract qualifies as a Low-Income Community (LIC) if it meets ANY of:

- Poverty rate >= 20%
- Median Family Income <= 80% of metro/state AMI
- Median Family Income <= 85% of state AMI (high migration rural counties)

Distress levels:

- deep       — the tract carries the CDFI Fund's **deep-distress** designation
- severe     — the tract carries the CDFI Fund's **severe-distress** designation
- lic        — NMTC eligible (meets LIC criteria) but not flagged severe/deep
- ineligible — Does not qualify
- unknown    — **indeterminate**: geocode no-match, or the tract is absent from
               the eligibility universe (paired with `nmtc_eligible = None`; never
               "ineligible")

> **How distress is determined.** For the official CDFI Fund file (the live
> `.xlsb` download), `severe_distress` and `deep_distress` are read **directly
> from the Fund's own pre-computed columns** — the package does not recompute
> them from ACS variables. The CDFI Fund's published criteria for those
> designations are, for reference, poverty >= 30% / MFI <= 60% AMI /
> unemployment >= 1.5x national (severe) and poverty >= 40% / MFI <= 50% AMI /
> unemployment >= 2x national (deep). A threshold-based fallback
> (`_compute_eligibility`) exists only for the generic CSV path and the built-in
> synthetic sample; it is **not** used for the official file.

---

## Data Sources

- CDFI Fund 2016-2020 ACS Low-Income Community Eligibility File
  https://www.cdfifund.gov/research-data
- US Census Bureau Geocoding API (free, no API key required)
  https://geocoding.geo.census.gov

---

## Output Columns

After running .enrich(), your DataFrame will have:

- nmtc_eligible (Optional[bool]: True / False / None — None = indeterminate)
- eligibility_status (str: verified-eligible / verified-ineligible / not-found / geocode-failed)
- distress_level (str: deep / severe / lic / ineligible / unknown)
- poverty_rate (Optional[float])
- ami_ratio (Optional[float])
- unemployment_rate (Optional[float])
- is_non_metro (bool)
- severe_distress (bool)
- deep_distress (bool)

---

## Known Issues

**`is_opportunity_zone` is unreliable — a `False` may be a vintage miss.** The
Opportunity Zone list is the CDFI Fund's Dec 2018 designated-QOZ file, and OZs
were designated on **2010 census tracts** (legally fixed to them). The geocoder
returns **2020** tracts, and **1,408 of the 8,764 OZ designations (~16%)** have
no matching 2020 GEOID (they split/merged/renumbered after 2010). So an address
in one of those designations reports `Opportunity Zone: No` even though it is in
a designated OZ. A **`Yes` is trustworthy**; a **`No` is not** — it may mean
"not an OZ" *or* "OZ with no 2020 GEOID", and the package cannot yet tell them
apart. This is **pre-existing** (not introduced or worsened by 0.4.1's geocoder
change). A tri-state fix (`Optional[bool]`) is slated for 0.5.0 — see the
CHANGELOG.

**`is_nmtc_native_area` is always `False` — it means "not determined," not "not
a native area."** No column in the live CDFI Fund `.xlsb` file feeds this field,
so it is `False` for all 85,395 tracts. Native areas (Federal Indian
Reservations, Off-Reservation Trust Lands, Hawaiian Home Lands, Alaska Native
Village Statistical Areas) are a real NMTC *Areas of Higher Distress* criterion,
but the CDFI Fund publishes it separately from the LIC eligibility file this
package loads. **Pre-existing since 0.1.0**; 0.4.1 does not change it. Resolution
deferred to 0.5.0 — see the CHANGELOG.

---

## Running Tests

    # docs-check: skip shell command; the suite is run by CI, not by this gate
    PYTHONPATH=. pytest tests/ -v

114 tests across all modules (including fail-loud, explicit-sample-mode,
tri-state eligibility, and async-batch coverage).

---

## Who This Is For

- CDEs screening project locations for NMTC eligibility
- CDFI analysts qualifying borrower locations at scale
- Researchers analyzing geographic distribution of LIC tracts
- Anyone replacing manual CIMS lookups with automated Python

---

## License

MIT 2026 Jay Patel
