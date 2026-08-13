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
one address at a time. nmtc-mapper automates this — pass a whole DataFrame of
addresses and get results in seconds, using the same official data source.

> **A batch is all-or-nothing, on purpose.** `enrich()` geocodes concurrently via
> `asyncio.gather` **without** `return_exceptions`, so the *first* transport
> failure or ambiguous address raises and **aborts the entire batch**. At 10,000
> addresses that is close to certain, so plan for a retry rather than for a
> partial frame. This is deliberate: the alternative — a silent per-row `None` —
> became a fabricated "ineligible" downstream, and losing time is strictly better
> than losing truth. A genuine no-match is *not* a failure and does not abort; it
> yields `eligibility_status = "geocode-failed"` for that row alone. Per-row
> failure capture needs a designed contract (which column carries the error, how
> `eligibility_status` reports transport failure vs no-match) and is **0.6.0's**.

---

## Installation

    # docs-check: skip shell installation command, not executable Python
    pip install nmtc-mapper

---

## Quickstart

    # docs-check: skip NMTCMapper() downloads the multi-MB CDFI Fund file and check_address hits the live Census geocoder
    from nmtcmapper import NMTCMapper, EligibilityResult

    mapper = NMTCMapper()

    # Single address (geocodes automatically) -> EligibilityResult
    result: EligibilityResult = mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")
    result.summary()
    print(result.nmtc_eligible)          # True / False / None (None = indeterminate)
    print(result.eligibility_status)     # "verified-eligible" | "verified-ineligible"
                                         #  | "not-found" | "geocode-failed"
    print(result.opportunity_zone_status)# "designated" | "not-confirmed" | "no-tract"
    print(result.distress_level)         # "deep" / "severe" / "lic" / "ineligible" / "unknown"
    print(result.poverty_rate)           # 0.38 — but see "Two kinds of missing" below

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

`EligibilityResult` is the return type of both `check_address()` and
`check_tract()` — a frozen-in-shape dataclass, exported from the top level so you
can type-annotate against it. It carries the fourteen fields listed under
[Output Columns](#output-columns) plus three read-only properties:
`eligibility_status`, `opportunity_zone_status` and `distress_description`.

Two loaders and the geocoder are exported directly, for callers who want the data
without the mapper:

    # docs-check: skip load_eligibility_table downloads the multi-MB CDFI Fund file; geocode_address hits the live Census API
    from nmtcmapper import load_eligibility_table, load_sample_table, geocode_address

    table = load_eligibility_table()      # the real 85,395-tract frame, indexed by GEOID
    demo  = load_sample_table()           # the 12-tract synthetic sample, offline
    tract = geocode_address("1234 S Michigan Ave, Chicago, IL 60605")   # -> "17031..." or None

`geocode_address` returns `None` for **exactly one** thing — a genuine no-match
(HTTP 200, zero address matches). Every other failure raises; see
[Exception hierarchy](#exception-hierarchy).

---

### What the eligibility percentage is a percentage *of*

`eligible_count(df)` returns counts plus **one** rate, and that rate's
denominator is named in its key:

| Key | Meaning |
|---|---|
| `total` | rows in the frame |
| `determined` | `nmtc_eligible` + `ineligible` — rows with a real verdict |
| `indeterminate` | `None` verdicts: no geocode match, or tract absent from the universe |
| `nmtc_eligible` | verified eligible |
| `ineligible` | verified ineligible — the Fund's file explicitly says NO |
| `pct_eligible_of_determined` | `Optional[float]`: `nmtc_eligible / determined`, **`None` when `determined == 0`** |
| `deep_distress` / `severe_distress` / `lic_only` | distress-tier counts |

**`pct_eligible` was removed in 0.5.0 and reading it now raises `KeyError`.** It
divided by `total`, which folds every indeterminate row into the denominator: on
1 eligible / 1 ineligible / 8 indeterminate it reported **10.0%** where the
eligible share of what was actually determined is **50.0%**. A rate over `total`
can only be read as "the other 90% are not eligible", which is a verdict for
eight rows no row was read for — and it moves with your address-formatting
quality rather than with eligibility. If you want the old lower-bound reading,
compute `nmtc_eligible / total` yourself from two returned keys; that direction
is explicit, the reverse was not recoverable.

`None` rather than `0.0` when nothing was determined, for the same reason: `0.0`
asserts "none of the determined rows are eligible" about an empty set.

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

### Exception hierarchy

Every class below is exported from the top level, so you can catch broadly or
precisely. All twelve names are spelled out — a glob like `*DownloadError` is a
gesture, and you cannot type a glob into an `except` clause.

    # docs-check: skip ASCII diagram of the exception hierarchy, not executable Python
    NMTCMapperError                    every error this package raises
    ├─ EligibilityDataError            the CDFI Fund eligibility dataset could not be obtained
    │  ├─ EligibilityDownloadError     403 / 404 / DNS / timeout / connection, no usable cache
    │  ├─ EligibilityParseError        obtained but unreadable: corrupt bytes, HTML error page, missing sheet, bad zip
    │  ├─ EligibilitySchemaError       read, but the layout moved: wrong column count, a renamed header at a bound index, or a degenerate parse — also raised by the cell-value allowlists
    │  └─ EligibilityValueError        a parsed number is outside its plausible bound (e.g. the AMI ratio flipping from ~0.91 to percent scale ~91)
    ├─ OZDataError                     the Opportunity Zone designation dataset could not be obtained
    │  ├─ OZDownloadError              403 / 404 / DNS / timeout / connection
    │  └─ OZParseError                 obtained but unreadable, or no recognizable tract column
    └─ GeocoderError                   address -> census tract resolution failed
       ├─ GeocoderTransportError       unreachable or unreadable after retries: HTTP status, timeout, connection/DNS, undecodable body
       └─ AmbiguousAddressError        multiple matches resolving to DIFFERENT tracts, so there is no single right answer

Catch at whatever level you mean:

    # docs-check: skip constructing NMTCMapper() downloads the CDFI Fund file
    from nmtcmapper import (
        NMTCMapper, NMTCMapperError,
        EligibilityDataError, EligibilityDownloadError, EligibilityParseError,
        EligibilitySchemaError, EligibilityValueError,
        OZDataError, OZDownloadError, OZParseError,
        GeocoderError, GeocoderTransportError, AmbiguousAddressError,
    )

    try:
        mapper = NMTCMapper()
        result = mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")
    except EligibilitySchemaError as e:
        raise SystemExit(f"CDFI Fund file layout changed; upgrade nmtc-mapper: {e}")
    except EligibilityDataError as e:
        raise SystemExit(f"No eligibility data: {e}")
    except AmbiguousAddressError as e:
        print(f"Needs a more specific address: {e}")
    except GeocoderTransportError as e:
        print(f"Census geocoder unreachable — retry later: {e}")
    except NMTCMapperError as e:
        raise SystemExit(f"nmtc-mapper failed: {e}")

`EligibilitySchemaError` refuses to parse on rather than read eligibility out of
an unverified column, and it offers **no bypass** — the verdicts it would let
through are not trustworthy. `AmbiguousAddressError` is raised only when the
candidate matches disagree; if every match resolves to the *same* tract the
ambiguity is harmless and the answer is returned. `GeocoderTransportError` is the
one a batch caller is most likely to meet, and it aborts the batch (above).

The shape of this tree is asserted by `tests/test_constraints.py`, not just
drawn here — the docs gate checks that each name appears in this file and
cannot check the inheritance relationships.

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
> A threshold-based rule (`_compute_eligibility`) backs the **built-in synthetic
> sample only**; it is **not** used for the official file. (Through 0.4.3 this
> sentence also named a "generic CSV path". There was no such path — the branch
> that also called this rule was unreachable dead code, and 0.5.0 deleted it.)

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

`.enrich()` adds **nine eligibility columns plus `eligibility_status`** — ten in
all — and removes nothing you passed in:

| Column | Type | Notes |
|---|---|---|
| `nmtc_eligible` | `Optional[bool]` | `True` / `False` / `None`. `None` = **indeterminate**, never a falsy "ineligible" |
| `distress_level` | `str` | `deep` / `severe` / `lic` / `ineligible` / `unknown` |
| `poverty_rate` | `Optional[float]` | may be `NaN` on a found tract — see below |
| `ami_ratio` | `Optional[float]` | may be `NaN` on a found tract — see below |
| `unemployment_rate` | `Optional[float]` | may be `NaN` on a found tract — see below |
| `is_non_metro` | `Optional[bool]` | `None` only when no row was read |
| `is_high_migration_rural` | `Optional[bool]` | `None` only when no row was read |
| `severe_distress` | `Optional[bool]` | `None` only when no row was read |
| `deep_distress` | `Optional[bool]` | `None` only when no row was read |
| `eligibility_status` | `str` | `verified-eligible` / `verified-ineligible` / `not-found` / `geocode-failed` |

The four `Optional[bool]` columns are `None` **exactly** when `eligibility_status`
is `not-found` or `geocode-failed`. For a found tract their `False` is the CDFI
Fund's published `NO` and is fully supportable. The frame is object-dtype, so
filter with `df[col] != True` — **`~df[col]` raises `TypeError`** once any
indeterminate row is present.

**`is_opportunity_zone` is not among them, and never has been.** Batch callers get
no OZ answer; single-address and single-tract callers do, via
`result.is_opportunity_zone` / `result.opportunity_zone_status`. 0.5.0
deliberately does not close that gap — adding a column is a data-surface change,
not an honesty fix.

**`is_nmtc_native_area` was removed in 0.5.0.** `df["is_nmtc_native_area"]` now
raises `KeyError`; see [Known limitations](#known-limitations).

### Two kinds of missing, in the three metric columns

`poverty_rate`, `ami_ratio` and `unemployment_rate` can be absent for **two
different reasons**, and the distinction is part of the contract:

- **`None`** — no row was read at all (`eligibility_status` is `not-found` or
  `geocode-failed`).
- **`NaN`** — a **found** tract whose metric the Fund published as `NA`: **1,583
  rows for poverty and 2,358 for AMI** on the live file. Those tracts still carry
  a real published YES/NO verdict; only the number is missing.

So `r.poverty_rate is None` is **not** a missing-value test on this field. Use
`pd.isna(r.poverty_rate)` for "no number either way", and `eligibility_status` to
tell which kind. `summary()` prints two different phrases for the two states —
*not available* for the Fund's `NA`, *tract not read* for an indeterminate result.
Through 0.4.3 both a wrongly-guarded `NaN` and the resulting `nan%` reached the
printed block.

---

## Opportunity Zone status

`is_opportunity_zone` is `Optional[bool]` and is **`True` or `None` — never
`False`** (0.5.0). Read `opportunity_zone_status` instead of the field's
truthiness; `summary()` does.

| `opportunity_zone_status` | `is_opportunity_zone` | What it asserts | Live count |
|---|---|---|---|
| `"designated"` | `True` | This GEOID is on the CDFI Fund's Dec-2018 designated-QOZ list. A claim about **the list**, which is 2010-tract-based — not about the parcel | 7,356 of 85,395 |
| `"not-confirmed"` | `None` | **Nothing.** The GEOID is not on that list, and this package cannot tell "not designated" from "designated on a 2010 GEOID with no 2020 successor" from "an Island Area outside this table" | 78,039 of 85,395 |
| `"no-tract"` | `None` | No census tract was resolved at all, so there was nothing to test membership against | when `tract_id is None` |

Three values, not four. The reasons behind `not-confirmed` are exactly what the
package **cannot** distinguish, so enumerating them as separate statuses would
re-introduce the fabrication in string form.

**Why `False` is not returnable.** The 2018 designations are legally fixed to
**2010** census tracts; this package's table and geocoder are **2020**-basis, and
**1,408 of the 8,764 designations (16.07%)** have no row in the 2020-basis table.
A non-match and a genuine non-designation are therefore *the same observation*
without a crosswalk, and no crosswalk ships: the 1,408 have 3,447 distinct 2020
successors, 1,299 of which also contain territory from 2010 tracts that were never
designated. Marking those `True` would assert a designation that was never made.

**Membership is keyed on the designation set, not on `tract_found`.** Pass one of
the retired 2010 GEOIDs directly and you get a correct `True` alongside
`tract_found = False` — the one place the OZ answer is more complete than the
eligibility answer.

**Upgrading from 0.4.3:** `if not r.is_opportunity_zone:` used to mean "not an OZ"
and now means "not confirmed" for **78,039 tracts**; `r.is_opportunity_zone is
False` now matches nothing, ever; `sum(...)` and `int(...)` over the field raise
`TypeError`. The CHANGELOG's UPGRADING table lists every call shape.

---

## Known limitations

**`is_nmtc_native_area` was removed in 0.5.0 — it is not tri-state, it is gone.**
Reading it raises `AttributeError` on a result, `KeyError` on an enriched frame,
and passing it to `EligibilityResult(...)` raises `TypeError`. **Tri-state where a
positive is obtainable; drop where it never is.** No value was ever obtainable:
the CDFI Fund publishes no tract-keyed NMTC native-area resource, and the four
AIANNH classes (Federal Indian Reservations, Off-Reservation Trust Lands,
Hawaiian Home Lands, Alaska Native Village Statistical Areas) carry four-digit
Census codes with **no state or county component**, so they cannot nest into
`SSCCCTTTTTT` at all — the Navajo Nation spans three states. Establishing the
status is a polygon intersection, not a table join. The criterion itself is live:
**Q32** of the CDFI Fund's *NMTC Compliance Monitoring and Evaluation Frequently
Asked Questions* (updated April 2025) names *NMTC Native Areas* as one of four
**Areas of Deep Distress** criteria; it is **not** among the eleven Areas of
Higher Distress resources Q31 lists. The field is gone because the package cannot
compute it, not because the criterion is unimportant. Use CIMS.

**A leading-zero-stripped GEOID silently returns not-found.** `check_tract()`
applies no normalization while both internal tables are `zfill(11)`-ed, so
`"1013953500"` — the standard form out of Excel and CSV — misses. It fails safe
(`nmtc_eligible = None`, never a fabricated `False`), but it is the most likely
real-world input error. Pass `str(geoid).zfill(11)` until **0.6.0** normalizes it.

**`opportunity_zone_status` says `not-confirmed` for input that was never a
GEOID.** `eligibility_status` correctly reports `not-found`, but the OZ property
tests only whether `tract_id is None`, so junk input takes the `not-confirmed`
branch. **0.6.0.**

---

## Bundled methodology

Decision documents for the eligibility contract ship **inside the distribution**,
not just in the repository, so they travel with the installed package.
`get_methodology_path()` resolves one:

    # docs-check: run methodology-path
    from nmtcmapper import get_methodology_path

    print(get_methodology_path().name)

`fabricated_negatives.md` (the default) records what a `False` asserts in every
boolean this package exposes, why `is_opportunity_zone` became `Optional[bool]`
while `is_nmtc_native_area` was dropped outright, and the regression invariants
those changes must not move.

---

## Running Tests

    # docs-check: skip shell command; the suite is run by CI, not by this gate
    PYTHONPATH=. pytest tests/ -v

192 tests across all modules (including fail-loud, explicit-sample-mode,
tri-state eligibility, fabricated-negative, null-sentinel-rendering,
percentage-denominator, exception-hierarchy-shape, cell-value-allowlist,
async-batch, cache-poisoning and schema-drift coverage).
14 of these are `@live` tests that hit the real CDFI Fund / Census endpoints; CI
deselects them with `-m "not live"`, leaving 178 offline.

---

## Who This Is For

- CDEs screening project locations for NMTC eligibility
- CDFI analysts qualifying borrower locations at scale
- Researchers analyzing geographic distribution of LIC tracts
- Anyone replacing manual CIMS lookups with automated Python

---

## License

MIT 2026 Jay Patel
