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

- Poverty rate >= 20%  — 26 U.S.C. §45D(e)(1)(A)
- Median Family Income <= 80% of metro/state AMI  — §45D(e)(1)(B)
- Median Family Income <= 85% of the applicable area AMI, for a tract in a
  **high migration rural county** — §45D(e)(5), added by section 223 of the
  American Jobs Creation Act of 2004. A high migration rural county is one with
  net out-migration of at least 10% of its population over the 20 years ending
  with the most recent census. 1,422 tracts carry this designation and 168 of
  them qualify on this route alone.

The CDFI Fund publishes the first two routes in the file's column C and the
third in column N, and has moved the boundary between those columns once (July
2026). nmtc-mapper reads the verdict as **C or N**, so it does not depend on
where the Fund currently draws it.

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
> designations are, for reference, poverty **> 30%** / MFI <= 60% AMI /
> unemployment >= 1.5x national (severe) and poverty **> 40%** / MFI
> **<= 40%** AMI / unemployment **>= 2.5x** national (deep). Each set is OR-ed
> internally and AND-ed with LIC. These are the workbook's own column headers,
> verbatim — `Severe distress=LIC AND (Poverty>30%; MFI<=60%;Unemployment>=1.5)`
> and `Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)`. The
> deep criteria read identically in the CDFI Fund's *NMTC Compliance Monitoring
> and Evaluation Frequently Asked Questions* (updated April 2025), **Q32**:
> poverty rates "greater than 40%", median family income that "does not exceed
> 40%", and "unemployment rates at least 2.5 times the national average".
>
> **LIC uses *at least*; distress uses *strictly greater*. That difference is
> deliberate — do not reconcile it.** The LIC poverty prong is `>= 20%` because
> §45D(e)(1)(A) defines it as a poverty rate "of at least 20 percent"; the
> distress poverty prongs are `> 30%` and `> 40%` because the Fund's column
> headers and FAQ Q32 say *greater than*. The boundary population is not
> hypothetical: 83 LIC tracts sit at exactly 30.0% poverty and 29 at exactly
> 40.0%. Of those qualifying on the poverty prong alone, the Fund published
> `severe = NO` for **all 21** at 30.0% and `deep = NO` for **all 13** at 40.0%.
>
> A threshold-based fallback (`_compute_eligibility`) exists only for the
> generic CSV path and the built-in synthetic sample; it is **not** used for the
> official file.

---

## Data Sources

- CDFI Fund 2016-2020 ACS Low-Income Community Eligibility File
  https://www.cdfifund.gov/research-data
- US Census Bureau Geocoding API (free, no API key required)
  https://geocoding.geo.census.gov

### What the eligibility universe covers — and what it does not

The CDFI Fund file holds **85,395 tracts: the 50 states, the District of
Columbia, and Puerto Rico (981 tracts)**. It contains **no rows for American
Samoa, Guam, the Northern Mariana Islands, or the US Virgin Islands** (state
FIPS 60, 66, 69, 78) — 133 census tracts on 2020 geography, zero of them in the
file.

That is a gap in a **named federal criterion**, not merely a coverage boundary.
FAQ Q32 (April 2025) enumerates "**US Island Areas**: Island Areas of the United
States, as determined by the United States Census Bureau including Puerto Rico,
U.S. Virgin Islands, Guam, the Commonwealth of the Northern Mariana Islands, and
American Samoa" as item 4 of the *Areas of Deep Distress* criteria. Puerto Rico
is named in that criterion **and** is in the file, so it is covered here like any
state. The other four are named in the criterion and are not in the file at all.

A tract in those four jurisdictions is therefore not `ineligible` — it is
**absent from the universe**, which this package reports as
`nmtc_eligible = None` / `distress_level = "unknown"`. Determine it against the
CDFI Fund's CIMS tool instead.

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
so it is `False` for all 85,395 tracts. A `False` from this field carries no
information at all: it never means the tract was checked and found not to be a
native area. Native areas (Federal Indian Reservations, Off-Reservation Trust
Lands, Hawaiian Home Lands, Alaska Native Village Statistical Areas) are a real
NMTC *Areas of **Deep** Distress* criterion — item 2 of the enumeration in
**Q32** of the CDFI Fund's *NMTC Compliance Monitoring and Evaluation Frequently
Asked Questions* (updated April 2025). They are **not** among the eleven Areas
of Higher Distress resources Q31 lists. The Fund publishes no tract-keyed lookup
for the criterion, and it is absent from the LIC eligibility file this package
loads. **Pre-existing since 0.1.0**; 0.4.1 does not change it. Resolution
deferred to 0.5.0 — see the CHANGELOG.

---

## Bundled methodology

Decision documents for the eligibility contract ship **inside the distribution**,
not just in the repository, so they travel with the installed package.
`get_methodology_path()` resolves one:

    # docs-check: run methodology-path
    from nmtcmapper import get_methodology_path

    print(get_methodology_path().name)

`fabricated_negatives.md` (the default) records what a `False` asserts in every
boolean this package exposes, why `is_opportunity_zone` becomes `Optional[bool]`
while `is_nmtc_native_area` is dropped outright, and the regression invariants
those changes must not move.

---

## Running Tests

    # docs-check: skip shell command; the suite is run by CI, not by this gate
    PYTHONPATH=. pytest tests/ -v

171 tests across all modules (including fail-loud, explicit-sample-mode,
tri-state eligibility, fabricated-negative, cell-value-allowlist, async-batch,
cache-poisoning and schema-drift coverage).
12 of these are `@live` tests that hit the real CDFI Fund / Census endpoints; CI
deselects them with `-m "not live"`, leaving 159 offline.

---

## Who This Is For

- CDEs screening project locations for NMTC eligibility
- CDFI analysts qualifying borrower locations at scale
- Researchers analyzing geographic distribution of LIC tracts
- Anyone replacing manual CIMS lookups with automated Python

---

## License

MIT 2026 Jay Patel
