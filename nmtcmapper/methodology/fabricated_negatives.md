# nmtc-mapper 0.5.0 — the fabricated-negative methodology

**Status:** decision document. Written before implementation, per the portfolio rule
for eligibility determinations under a federal tax credit. No production behaviour
changes with this document; nothing here bumps a version, moves a tag, or publishes.

**Scope:** every boolean this package exposes, and what a `False` in each of them
actually asserts. In scope: `is_opportunity_zone`, `is_nmtc_native_area`, the six
other booleans nobody had audited, the rendering and serialisation sites, the
upgrade path, `_compute_eligibility()`'s blast radius, the docs-check ledger, and
the `cdfi-superpowers` sync. Out of scope and untouched: the 0.4.2 verdict logic
(column C **or** column N), the exact-header validation, the `nmtc_eligible`
tri-state, OZ 2.0 (`docs/oz2-methodology.md` is a separate decision document about a
different question), and every eligibility number.

---

## 0. What was executed, and against what

Every figure below was derived in this session. Nothing is carried forward on
trust — including the figures this package already publishes.

| Artefact | Identity | SHA-256 |
|---|---|---|
| Eligibility table | `NMTC_LIC_Eligibility_2016_2020.xlsb`, sheet `2016-2020`, 85,395 data rows, 4,811,307 bytes (CDFI Fund `NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb`, July-2026 re-publish) | `3a6f5851…428772d49` |
| OZ designations | `QOZ_Designated_2018.xlsx`, sheet `QOZs 14Jun`, 276,974 bytes (CDFI Fund `designated-qozs.12.14.18.xlsx`) | `96b791f3…b170891` |
| 2020 tract universe | Census `2020_Gaz_tracts_national.txt` (2020 Gazetteer), 85,395 GEOIDs | fetched 2026-08-09 |
| 2010 tract universe | Census `Gaz_tracts_national.txt` (2010 Gazetteer), 74,002 GEOIDs | fetched 2026-08-09 |
| Tract relationship | Census `tab20_tract20_tract10_natl.txt` (2020↔2010 tract relationship file), 85,528 × 74,134 | fetched 2026-08-09 |
| AIANNH universe | Census `2020_Gaz_aiannh_national.txt`, 334 entities | fetched 2026-08-09 |
| Compliance FAQ | *NMTC Compliance Monitoring and Evaluation — Frequently Asked Questions*, cover page: "**UPDATED APRIL 2025**"; running footer: "CDFI FUND \| NMTC Compliance & Monitoring FAQs \| April 2025"; 64 pages | `8d75e98a…7a0b806a` |

Repository state at the time of writing: branch `docs/0.5.0-methodology` cut from
`main` at `1485923`, which is the commit the annotated tag `v0.4.2` points to.
Seven tags. `pyproject.toml` version `0.4.2`. PyPI latest `0.4.2` (queried; the
project has twelve releases on PyPI and seven tags — `0.1.0` through `0.3.0`
predate tagging). 140 tests collected.

Two commands reproduce the core of M1 and M7:

```
# M7 invariants + M1 vintage miss
python - <<'PY'
from nmtcmapper.data.loader import load_eligibility_table, load_opportunity_zones
df, oz = load_eligibility_table(), load_opportunity_zones()
print(len(df), int(df.nmtc_eligible.sum()), df.distress_level.value_counts().to_dict())
print(len(oz), len(oz - set(df.index)), len(oz & set(df.index)))
PY
# -> 85395 35335 {'ineligible': 50060, 'lic': 14153, 'severe': 13121, 'deep': 8061}
# -> 8764 1408 7356
```

---

## 1. The finding that organises the release

0.4.0 established a tri-state contract for the verdict — `nmtc_eligible` is
`Optional[bool]`, `distress_level` gains `"unknown"`, `eligibility_status` names
the four outcomes — and left every other boolean a bare `bool` whose `False`
means "unknown". The package documents this in its own source and ships it
anyway:

```python
# eligibility/checker.py
    # A `False` here may be a VINTAGE MISS, not "not an OZ" … a `True` is
    # trustworthy; a `False` is not distinguishable from "not an OZ".
    is_opportunity_zone: bool = False

    # ALWAYS `False`: no column in the live CDFI Fund .xlsb populates this, so a
    # `False` means "not determined," NOT "confirmed not a native area".
    is_nmtc_native_area: bool
```

This is the fourth instance of the pattern in this portfolio — `oz-tracker` 0.1.0
(8,756 of 8,764 designated OZs returned a confident `False`), `sbic-tracker` 0.1.0,
`cdfi-fund-tracker` 0.1.0. And the `nmtc-eligibility` skill's own non-negotiable
third-state rule says a fabricated negative "kills a deal that may genuinely
qualify," and that "a false 'ineligible' is exactly as damaging as a false
'eligible,' in the opposite direction." `is_opportunity_zone` violates that rule
inside the object the rule is written about.

**M3 found that the scope is larger than two fields, and in a place nobody looked.**
The two commented fields are not the whole defect. The two code paths 0.4.0 wrote
*specifically* to avoid fabricating a verdict — the tract-absent branch of
`check_tract()` and the geocode-failure branch of `check_address()` — set `False`
on **every** boolean they return. See §M3.

### The decisions

1. **`is_opportunity_zone` becomes `Optional[bool]`.** `True` when the GEOID is in
   the 2018 designation set; `None` otherwise. `False` is never returnable.
2. **`is_nmtc_native_area` is dropped**, not made tri-state.
3. **Methodology first, then one build carrying the whole release.**

All three survive contact with the data. §M2 states the principle that separates
(1) from (2); §M3 extends both remedies to the fields the brief did not name;
§M6 confirms the deferred `_compute_eligibility()` defects do not displace them.

---

## M1 — The OZ rule, and the figure it rests on

### M1.1 The vintage miss, derived

The 2018 designations are 2010-tract-based. The eligibility table and the bound
geocoder are 2020-basis (`schema.TRACT_VINTAGE`: `basis_year=2020`,
`geocoder_vintage="Census2020_Current"`, `table_geoid_header="2020 Census Tract
Number FIPS code. GEOID"`).

| Quantity | Value |
|---|---|
| OZ designations loaded from `designated-qozs.12.14.18.xlsx` | **8,764** |
| Present in the 85,395-tract 2020-basis table | **7,356** (83.93%) |
| **Absent — no row in the 2020-basis table** | **1,408** |
| **Percentage** | **16.07%** |

Command:

```
python -c "
from nmtcmapper.data.loader import load_eligibility_table, load_opportunity_zones
t = set(load_eligibility_table().index); oz = load_opportunity_zones()
print(len(oz), len(oz - t), 100*len(oz - t)/len(oz))"
# 8764 1408 16.065...
```

The figure the package already publishes (1,408 / ~16%) is correct. It was
re-derived, not carried.

### M1.2 The miss is not one thing, and the README says it is

The package's README attributes all 1,408 to tracts that "split/merged/renumbered
after 2010." Checked against the Census universes, that is true of most of them
and false of 76:

| Class | Count | What it is |
|---|---|---|
| 2010 GEOID retired at the 2020 vintage | **1,332** | Genuine vintage miss: the tract exists in the 2010 gazetteer and in the relationship file, and has no 2020 tract of the same code. |
| **Island Areas** (FIPS 60, 66, 69, 78) | **75** | American Samoa, Guam, CNMI, USVI. These are **not in the Fund's table at any vintage** — the 2016–2020 ACS did not cover them, and the Fund publishes Island Areas LIC eligibility in a separate file (`NMTC_LIC_Territory_2020_December_2023.xlsx`) built on the 2020 Island Areas Decennial Census. Their absence is a coverage hole, permanent, and has nothing to do with tract vintage. It is also a gap in a **named federal criterion**, not merely in coverage: FAQ Q32 enumerates *"4) US Island Areas: Island Areas of the United States, as determined by the United States Census Bureau including Puerto Rico, U.S. Virgin Islands, Guam, the Commonwealth of the Northern Mariana Islands, and American Samoa"* as one of the four Areas of Deep Distress criteria. Puerto Rico falls inside that criterion **and** inside the Fund's table, so the 75 uncovered tracts are the four non-PR Island Areas only — but for those four the package cannot evaluate a criterion the Fund has published. |
| Not a valid tract at either vintage | **1** | `51019050100` — present in the OZ designation file, absent from the 2010 gazetteer, absent from the 2010 side of the relationship file, absent from the 2020 table. A defect in the source designation list, not in this package. |

The `nmtc-eligibility` skill already documents the Island Areas hole correctly
(§"Island Areas are a second scope hole of the same class"); the package README
does not, and folds those 75 into a vintage explanation that does not apply to
them. **0.5.0 corrects the README to the three-way split.** The user-visible
answer is `None` in all three cases, so this changes no behaviour — it changes what
the package says is true, which is the whole subject of this release.

### M1.3 Why the `True` direction is safe — with the limit stated

The brief takes "a `True` is trustworthy" as settled. It is trustworthy *as the
assertion the package is entitled to make*, and that assertion is narrower than
"this address is in an Opportunity Zone."

A `True` asserts: **the 11-digit GEOID this lookup resolved to appears verbatim on
the CDFI Fund's December-2018 list of designated Qualified Opportunity Zones.**
That is a closed-set membership test with no inference in it. There is no
false-positive mechanism at the level of the code: the designation list is a fixed
enumeration, the comparison is string equality after `zfill(11)`, and nothing
derives, interpolates, or infers.

The residual limit is geographic, not logical, and it is measurable. A 2020 tract
that keeps a 2010 tract's code usually keeps its territory — but not always. Using
the Census 2020↔2010 tract relationship file, for each of the 7,356 matched GEOIDs,
what share of the 2020 tract's land came from the identically-numbered 2010 tract:

| Share of the 2020 tract's land inherited from the same-numbered 2010 tract | Tracts |
|---|---|
| ≥ 99.9% | 6,027 |
| 99% – 99.9% | 802 |
| 90% – 99% | 453 |
| 50% – 90% | 71 |
| < 50% | 3 |
| **Below 99%** | **527 (7.2%)** |

The extreme case is `42063961102`: only **12.4%** of the 2020 tract's land came
from the 2010 tract of the same number. An address in the other 87.6% gets a
`True` for a designation that does not cover the ground it stands on.

This does not change the decision — `True`/`None` remains correct, and the
alternative (suppressing 527 true positives) is worse. It changes what the
package may *say*. **0.5.0's README, the skill, and `summary()`'s rendered `YES`
line (§M4.2) state the `True` direction as a claim about the designation list, not
about the parcel**, and note that for
roughly 7% of matches the 2020 tract's boundary differs materially from the
designated 2010 tract. That is the honest form of "a `Yes` is trustworthy."

### M1.4 The rule's real reach — the number that belongs in the CHANGELOG

The headline (1,408 unreachable designations) understates the release. The rule is
not "1,408 designations become `None`"; it is "**every non-match becomes `None`**,"
because a genuine non-designation and a vintage miss are the same observation
without a crosswalk.

| | Today | 0.5.0 |
|---|---|---|
| Tracts in the table that return `is_opportunity_zone=True` | 7,356 | 7,356 (unchanged) |
| Tracts in the table that return `is_opportunity_zone=False` | **78,039** | **0** |
| Tracts in the table that return `is_opportunity_zone=None` | 0 | **78,039** |

**78,039 of 85,395 tracts (91.4%) change their returned value.** That is the
release's user-visible impact and it belongs in the document, the CHANGELOG's
upgrade table, and the skill — not the 1,408, which is only the subset where the
old `False` was demonstrably wrong rather than merely unsupportable.

**The obvious objection, named and answered: `None` for nine tracts in ten is a lot,
and the field still earns its place.** A reader who watches 91.4% of a lookup's
answers turn into "unknown" is entitled to ask whether the lookup is worth shipping.
It is, for a structural reason rather than a consoling one: **the OZ test is keyed on
the designation set, not on the eligibility table.** `is_opportunity_zone` is computed
as `tract_id in self._oz_tracts`, evaluated independently of `tract_found`
(`mapper.py:118`, `mapper.py:137`). The field therefore returns `True` for **all 8,764
designations** when a caller passes a GEOID directly — not merely the 7,356 that also
have a row in the 2020-basis table. Verified by execution this session:
`check_tract()` over all 8,764 designated GEOIDs returns `is_opportunity_zone=True`
**8,764 times**, including for each of the 1,408 that return `tract_found=False`
(e.g. `01003011502` → `is_opportunity_zone=True`, `tract_found=False`,
`eligibility_status='not-found'`). The 91.4% is a property of *the table's tract
universe*, which is the wrong denominator for judging the OZ field: the 78,039 are
overwhelmingly tracts that were never designated, and `None` is the honest answer for
each of them, because a non-designation and a vintage miss are the same observation
without a crosswalk (§M1.5).

The portfolio has already accepted this trade in a stronger form. `oz-tracker` 0.2.0
— prepared, version set in `pyproject.toml`, and deliberately **not** published —
makes `is_designated()`, `is_eligible()` and `is_rural()` return `True` or `None` and
never `False`, and its checkers raise on essentially every call because both upstream
sources return HTTP 404. Its CHANGELOG states the rule this release applies one
package over: *"a package that says 'I cannot answer' is strictly better than one that
answers wrong."* A lookup that is largely non-functional **by design** is a coherent
artefact when the alternative is one that is confidently wrong. What is not coherent
is a lookup that hides the ratio. 0.5.0 publishes the ratio.

Two paths outside the table are also affected and must be changed with it:

- `NMTCMapper.check_address()` sets `is_opportunity_zone=False` explicitly on the
  geocode-no-match branch (`mapper.py:114`). No tract was resolved; there is
  nothing to test membership against. → `None`.
- `NMTCMapper.check_tract()` and `check_address()` both compute
  `tract_id in self._oz_tracts` **regardless of `tract_found`** (`mapper.py:118`,
  `mapper.py:137`). A caller passing one of the 1,408 retired 2010 GEOIDs directly
  gets `is_opportunity_zone=True` alongside `tract_found=False`. That combination
  is correct and should be preserved: the GEOID *is* designated; the package simply
  has no 2016–2020 eligibility row for it. It is the one place the OZ answer is
  more complete than the eligibility answer, and it must not be collateral damage.

### M1.5 The crosswalk exclusion, argued on its own terms

`hmda-analyzer` 0.6.0 rejected bundling a 2010↔2020 crosswalk because HMDA carries
no sub-tract location and conversion produces fractional loan counts. **That
argument does not transfer.** Here a crosswalk would scope uncertainty, not convert
values: it would tell you which 2020 tracts descend from a designated 2010 tract.
So the case has to be made on different grounds. Three, in descending strength:

**(a) A relationship file answers a different question than the one asked.**
Designation under §1400Z-1 is a legal act performed on a specific enumerated 2010
tract. It was not performed on the 2020 tracts that inherit that land. Measured on
the 1,408: they have **3,447 distinct 2020 successors**, of which 3,356 are in the
Fund's table, and **1,299 of those (38.7%) also contain territory from 2010 tracts
that were never designated.** Marking those 3,356 `True` would assert a designation
that was never made, for tracts nearly 40% of which are demonstrably part
non-designated. Marking them `None` — which the rule already does, since they are
non-matches — is exactly right, and requires no crosswalk to achieve. **A crosswalk
would let the package say more, and everything extra it could say would be an
inference presented as a designation.**

The symmetric measurement makes the same point from the other side: **2,511 tracts
in the table that are not on the designation list draw at least half their land
from designated 2010 OZ territory.** Under the 0.5.0 rule they are `None`, which is
the correct answer for all 2,511. Under a crosswalk, someone has to pick a land-share
threshold — and that threshold, not the statute, would decide whether a deal's tract
"is" an OZ.

**(b) Maintenance burden and vintage drift.** The relationship file is 18.7 MB for
one vintage pair. The 2030 decennial produces a new tract basis, at which point the
package needs 2010↔2020↔2030 chaining and the share-threshold problem compounds at
every hop.

The OZ 2.0 half of this argument was carried uncited, and it was wrong. It is
corrected here rather than deleted. The date is real and now sourced: **Rev. Proc.
2026-14** (effective April 6, 2026) provides the procedure for nominating tracts to
be designated as QOZs **effective January 1, 2027**, and Treasury's Office of Tax
Analysis published the eligibility and rural methodologies for those designations
under **§70421 of the One Big Beautiful Bill Act** in March 2026 — all read and
digest-pinned in `docs/oz2-methodology.md` §0 (S1, S3, S4), the sibling decision
document for that question.

What was wrong is the clause attached to the date. OZ 2.0 is **not** on a newer
tract *basis*. Rev. Proc. 2026-14 §3.01(3) fixes the eligible tracts' boundaries to
those "**established for the 2020 decennial census**" — the same decennial basis
this package already uses. The difference is one of *scheme*, not basis: Treasury's
own rural methodology (S4, footnote 10) directs readers to combine the eligible-tract
list with the **2024 TIGER** census-tract map, so the Appendix's keys are the 2024
annual vintage of the 2020 delineation, which `docs/oz2-methodology.md` shows is not
pointwise identical to the 2020 delineation as first published.

Corrected, the point survives in weaker but still usable form. A 2010↔2020 crosswalk
would *not* be obsoleted by OZ 2.0, since OZ 2.0 shares the 2020 basis — so that is
**not** a reason the next release would have to re-derive it. It remains a reason not
to trust a crosswalk's keys across releases, because scheme drift *inside* one basis
is precisely the failure the portfolio's tract-vintage methodology formalises as
*scheme strictly dominates basis*. Ground (b) is the second-strongest of the three
either way; **(a) — the 38.7% mixed-descent measurement — is the load-bearing
evidence and is untouched by this correction.**

**(c) It is not the package's determination to make.** The CDFI Fund's own answer
to "I can't find a 2010 census tract in the 2016-2020 ACS data" (*2016-2020 ACS
Data FAQ*, updated Feb 1 2024, Q10) routes the reader to the Census tract
relationship files and to CIMS. Routing is the correct behaviour for a lookup tool
whose contract is "no unverifiable assertions." The package should name the
relationship file in the `None` explanation, and not consume it.

**Conclusion: the exclusion holds, and it holds more strongly than the brief
assumed** — not because a crosswalk is technically awkward, but because every
answer it would produce is a different kind of claim than the one `is_opportunity_zone`
is supposed to make. The 38.7% mixed-descent figure is the load-bearing evidence,
and it should appear in the CHANGELOG rather than a bare "crosswalk out of scope."

---

## M2 — Why `is_nmtc_native_area` is dropped rather than made tri-state

### M2.1 The principle

> **Tri-state where a positive is obtainable. Drop where it never is.**

A field that can only ever say "I don't know" is not honesty, it is noise — and it
invites a downstream consumer to treat its absence of `True` as meaningful. Two
fields, two remedies, from one rule:

| | `is_opportunity_zone` | `is_nmtc_native_area` |
|---|---|---|
| Is a `True` obtainable? | Yes — 7,356 of 85,395 tracts, today, from a bundled source | **No.** Zero of 85,395, from any source this package loads, ever |
| What does a tri-state field carry? | Real information in one direction | `None` for all 85,395 rows, forever |
| Remedy | `Optional[bool]` | Removal |

There is a second, mechanical argument for removal over tri-state, and it belongs
in the document because it is the reverse of the defect this release exists to fix:
**dropping a field fails loud.** `result.is_nmtc_native_area` becomes an
`AttributeError`; `EligibilityResult(..., is_nmtc_native_area=False)` becomes a
`TypeError`. A tri-state field fails silent — `if result.is_nmtc_native_area:`
keeps running and keeps meaning the wrong thing. Where a field carries no
information at all, the loud failure is the feature.

### M2.2 No value is ever obtainable — re-verified from the source's own header

The primary citation was re-verified this session, from the document's own header
rather than a URL label. A prior cycle in this portfolio cited a superseded FAQ as
primary; this one is checked.

**Document:** cover page reads "NEW MARKETS TAX CREDIT / FREQUENTLY ASKED QUESTIONS
/ **UPDATED APRIL 2025** / COMPLIANCE MONITORING AND EVALUATION"; every page footer
reads "CDFI FUND | NMTC Compliance & Monitoring FAQs | April 2025"; 64 pages;
SHA-256 `8d75e98a…7a0b806a`.

**Q31** ("What resources are available to determine if a census tract is in an
approved Area of Higher Distress?") enumerates exactly **eleven** resources the
Fund links from its Compliance Monitoring and Evaluation page:

Brownfield Sites · SBA Designated HUB Zones · Federal Medically Underserved Areas
or geographic HPSA · Appalachian Regional Commission Distressed Counties and Areas
· Delta Regional Authority Distressed Counties and Parishes · Low-Income and
Low-Access census tracts to supermarkets · Promise Zone · FEMA Disaster Declaration
Areas · Impacted Coal Counties · Base Realignment and Closure (BRAC) Sites ·
Qualified Opportunity Zones.

**Native Areas is not among them.** The brief's claim is accurate.

### M2.3 A correction the brief's citation conceals — and it strengthens the case

**Q32, the next question, does name it.** Verbatim, in the enumeration of the
Areas of *Deep* Distress criteria added in the CY 2024-2025 Application:

> "2) **NMTC Native Areas**: Federal Indian Reservations, Off-Reservation Trust
> Lands, Hawaiian Home Lands, and Alaska Native Village Statistical Areas."

Three consequences:

1. **The criterion is live and recently added** — it is a CY 2024-2025 Application
   commitment category, not a legacy artefact. "No source exists or is coming" is
   too strong; what Q31 establishes is that the Fund publishes **no tract-keyed
   lookup resource** for it while treating it as a compliance category. That is the
   claim 0.5.0 should make.
2. **The package's current docs mis-categorise it.** The README, the CHANGELOG
   (0.4.1), and the skill all call Native Areas an *Areas of Higher Distress*
   criterion. Per this FAQ it is enumerated under **Areas of Deep Distress**. All
   three must be corrected in 0.5.0.
3. **The drop decision is unaffected, and better founded.** The field is being
   removed because the package cannot compute it, not because the criterion is
   unimportant. If the Fund ever publishes a tract-keyed file, the field returns as
   a real field with real `True` values — which is a cleaner re-entry than
   un-deprecating an always-`None` column.

### M2.4 Why the determination is a spatial intersection, not a join

The four classes are Census AIANNH legal geographies. They do not nest to census
tracts, and the Census Bureau's own identifiers say so: in the 2020 AIANNH
Gazetteer the GEOID is a **four-digit AIANNH census code with no state or county
component** (e.g. `2430` = Navajo Nation Reservation and Off-Reservation Trust
Land, 24,429 sq mi; `0010` = Acoma Pueblo and Off-Reservation Trust Land). A census
tract GEOID is `SSCCCTTTTTT` — state, then county, then tract. An entity whose
identifier carries no state cannot sit inside the state→county→tract nesting chain,
and the Navajo Nation in fact spans three states.

So establishing native-area status for a tract is a **polygon intersection**
(TIGER/Line AIANNH shapefiles against TIGER/Line tract shapefiles), not a table
join on a key. That means: a geospatial dependency stack this package does not
have, a coverage decision (any overlap? centroid? majority land?) **that the Fund has
not published a rule for under NMTC**, and an answer this package would be inventing.
Removing the field is the only option that does not require the package to make up a
methodology for a federal compliance category.

The NMTC qualifier in that sentence is load-bearing, and the general form of the claim
would have been overstated. The Fund *does* perform tract-keyed native-area
qualification — for other programs. Its CIMS map service
(`/arcgis/rest/services/PN/CIMS3_PN_View/MapServer`, 88 layers, enumerated this
session) carries **`Native American IA Qualifying Tract`** (layer 39, with 2016-2020
variants at 102-104 and an FY2014 variant at 59) and **`Native American BEA Qualifying
Tract`** (layer 38, with `Native BEA FY2014 Qualified Tract` at 10) — tract-level
*qualification* layers for Native Initiatives and the Bank Enterprise Award. The NMTC
layer family in the same service is `2016-2020 NMTC Census Tracts` (91), `2016-2020
NMTC Qualified Census Tracts` (94) and their 2006-2010 / 2011-2015 predecessors
(45-50), and it has **no native-area member**. The underlying geographies are
published in the same service too (`Native American Areas`, 37; `Federal Indian
Reservation`, 41), so the absence is not one of source data.

That is a stronger and narrower fact than "the Fund has not published a rule": the
Fund has published a tract-keyed native-area determination **twice, for two other
programs, and not for NMTC**. It also makes a future NMTC source plausible rather than
speculative — which is exactly the condition §M2.3(3) sets for the field returning as
a real field with real `True` values.

---

## M3 — The full boolean sweep

This is the section the brief predicted would find something it did not know
about. It did.

### M3.1 What was swept

Every boolean the package exposes, on every surface: `EligibilityResult` fields,
the `check_tract()` return dict, the columns `enrich_dataframe()` writes, and the
columns `load_eligibility_table()` produces. **Nine distinct boolean fields**
across four surfaces. Function *parameters* that happen to be booleans
(`force_reload`, `force`, `use_async`) are inputs, not assertions about a tract,
and are out of scope.

Two facts had to be established before any field could be judged, because the
answer for six of them depends on it:

**(a) The source columns are strict binaries with no nulls.** Across all 85,395
rows of the live workbook:

| Column | Distinct raw values | Counts |
|---|---|---|
| 1 — OMB Metro/Non-metro | `Metro`, `Non-metro` | 71,554 / 13,841 |
| 2 — LIC (col C) | `NO`, `YES` | 50,060 / 35,335 |
| 13 — High Migration Rural (col N) | `NO`, `YES` | 83,973 / 1,422 |
| 14 — Severe distress (col O) | `NO`, `YES` | 64,213 / 21,182 |
| 15 — Deep distress (col P) | `NO`, `YES` | 77,334 / 8,061 |

No blanks, no `NA`, no third value, in any of the five. **This is what makes a
`False` supportable for a found tract: it is the Fund's published `NO`, not a
default.**

**(b) Null demographics do not weaken the published flags.** 1,583 rows have `NA`
poverty and 2,358 have `NA` MFI (the documented class including `11001980000`).
Restricted to the 2,750 rows with either null, all five columns are still strict
`YES`/`NO` — 876 of them are `YES` on column C, 735 `YES` on severe, 555 `YES` on
deep. The Fund reached a determination for those tracts and published it. On the
**live** path the package reads that determination rather than recomputing it, so a
null poverty rate does not produce a fabricated `False`. (On the **sample** path it
does — `pr >= threshold` is `False` for `NaN` — but that path is
`_compute_eligibility()`; see §M6.)

### M3.2 The sweep table

For each field: what a `True` asserts and on what evidence; what a `False`
asserts and whether the package can support it; and the remedy.

**Path A — tract found in the table** (`check_tract()` hit, `tract_found=True`):

| # | Field | `True` asserts / evidence | `False` asserts — supportable? | Remedy |
|---|---|---|---|---|
| 1 | `nmtc_eligible` *(already tri-state)* | Column C **or** column N is `YES` — the Fund's LIC determination | Both are `NO`. **Yes** — a published `NO`, verified strict-binary | None needed (0.4.0) |
| 2 | `is_non_metro` | Column 1 ≠ `Metro` | Column 1 is `Metro`. **Yes** today — but see §M3.3, the parse is a not-equal test | Keep; harden the parse |
| 3 | `is_high_migration_rural` | Column N is `YES` — an LIC *determination* under §45D(e)(5) (0.4.2) | Column N is `NO`. **Yes** — published, strict-binary | Keep; harden the parse (§M3.3) |
| 4 | `severe_distress` | Column O is `YES` — the Fund's published severe-distress designation | Column O is `NO`. **Yes** — published, strict-binary, and unaffected by null demographics | Keep; harden the parse (§M3.3) |
| 5 | `deep_distress` | Column P is `YES` — the Fund's published deep-distress designation | Column P is `NO`. **Yes** — same | Keep; harden the parse (§M3.3) |
| 6 | `is_nmtc_native_area` | **Nothing. Never `True`** — 0 of 85,395; hardcoded `False` at `loader.py:405` | "Not determined." **No** — the package has no source and can never have one from this file | **DROP** (§M2) |
| 7 | `is_opportunity_zone` | The GEOID is on the Dec-2018 designation list | "Not designated" **or** "vintage miss" **or** "Island Area outside this table". **No** | **`Optional[bool]`** (§M1) |
| 8 | `tract_found` | A row for this GEOID exists in the loaded table | No row exists. **Yes** — it is a statement about the table, not the world, and the table is fully enumerated | Keep |
| 9 | `geocode_success` | *Nominally*: the address resolved to a tract | Geocoding returned no match. **Yes** on `check_address()`. **See §M3.4** — on `check_tract()` it is set `True` with no geocode performed | Keep the field; fix the claim |

**Path B — tract absent, or address did not geocode.** This is the finding.

`check_tract()`'s lookup-miss branch (`checker.py:120-132`) and
`check_address()`'s no-match branch (`mapper.py:99-115`) are the two code paths
0.4.0 wrote *specifically* to stop the package fabricating a verdict. They set
`nmtc_eligible=None`, `distress_level="unknown"`, all three metrics to `None`, and
`tract_found=False`. And then they set **every remaining boolean to `False`**:

```python
# eligibility/checker.py:120  — the branch whose own comment says INDETERMINATE
    "is_non_metro": False,
    "is_high_migration_rural": False,
    "is_nmtc_native_area": False,
    "severe_distress": False,
    "deep_distress": False,
```

| # | Field | What `False` asserts on an absent tract | Supportable? |
|---|---|---|---|
| 2 | `is_non_metro` | "This tract is in a metropolitan area" | **No.** No row was read |
| 3 | `is_high_migration_rural` | "This tract is not in a high migration rural county" | **No** |
| 4 | `severe_distress` | "The CDFI Fund did not designate this tract severely distressed" | **No** |
| 5 | `deep_distress` | "…nor deeply distressed" | **No** |
| 6 | `is_nmtc_native_area` | — | **No** (dropped anyway) |
| 7 | `is_opportunity_zone` | On the geocode-failure branch only: "not an OZ", with no tract in hand | **No** |

**Six fabricated negatives per indeterminate result on the geocode-failure branch,
five on the `check_tract()` miss — in the two branches built to prevent exactly
that.** The count differs by one because `is_opportunity_zone` is not among the
booleans `check_tract()`'s miss branch sets: on that path a real membership test runs
against a real GEOID (`tract_id in self._oz_tracts`, `mapper.py:137`) and its answer
is correct — that is the §M1.4 carve-out. Only the geocode-failure branch, which has
no GEOID in hand at all, fabricates the sixth. The §M3.2 table above is precise on
this; it was the bolded summary that rounded both branches up to six. The tri-state
work stopped at the verdict; the supporting
booleans it left behind still speak with full confidence about a tract the package
never read. A downstream consumer filtering `df[~df.is_high_migration_rural]` or
reading `result.severe_distress` off an unknown tract gets a confident wrong
answer, and `eligibility_status` — the field designed to make the indeterminate
case impossible to miss — is on a different attribute.

**Remedy: `Optional[bool]` for fields 2, 3, 4 and 5, `None` on both indeterminate
branches.** Not because a `False` is unobtainable for them — it is perfectly
obtainable, from a published `NO`, whenever a row exists — but because on these two
branches no row exists. This is the same rule as §M2, applied per-observation
instead of per-field: tri-state where a positive is obtainable.

That is the correct scope, and it is larger than the brief's. It also makes the
release internally consistent: after 0.5.0, an indeterminate `EligibilityResult`
has no field that claims to know anything about the tract.

### M3.3 `is_non_metro`: right answer, wrong guard

```python
non_metro = str(vals[1]).strip().upper() != "METRO"     # loader.py:368
```

This is a **not-equal** test, so every unrecognised value maps to `True`. Today
that is invisible: column 1 holds only `Metro` and `Non-metro`. But if the Fund
ever publishes a blank, an `NA`, or a third designation, 0.5.0's package silently
reports those tracts as non-metro. The header guard does not catch it — the guard
pins header *strings*, not cell vocabularies, and a value change leaves the header
untouched.

The direction matters because `is_non_metro` is the field `_compute_eligibility()`
uses to widen the LIC income band to 85% (§M6), so a fabricated `True` is
over-inclusive on eligibility on the sample path, and over-inclusive on the live
path the day the Fund reuses that column.

**Remedy (0.5.0, non-breaking):** parse as an explicit two-way match —
`"NON-METRO"` → `True`, `"METRO"` → `False`, anything else raises
`EligibilitySchemaError` with the offending value and row index, exactly as the
value-bounds guard does for numerics. This costs nothing today (0 rows affected,
invariants unmoved) and closes a silent-drift channel the header guard structurally
cannot see.

**The same treatment is decided — not "considered" — for columns N, O and P.** Their
`== "YES"` tests map every unrecognised value to `False`: `'Y'` parses to `False`
today. Hardening column 1 alone would harden the one column that drifts toward a
**false positive** and leave at "consider" the three that drift toward **false
negatives**, which is backwards relative to this document's entire thesis — the
fabricated negative is the defect the release exists to close, and N/O/P are where a
vocabulary change would produce one. 0.5.0 therefore gives all four columns a value
allowlist: `{"YES", "NO"}` for N/O/P and `{"METRO", "NON-METRO"}` for column 1,
matched after the existing `strip().upper()` normalisation, with anything else raising
`EligibilitySchemaError` naming the column, the offending value and the row index. As
with column 1 this is 0 rows affected today and no invariant moves (§M3.1a re-verified
all five columns strict-binary across 85,395 rows).

One structural point applies to all four and is worth stating once, because it is why
these guards are not redundant with the ones already shipped: **the header guard pins
header *strings*, not cell *vocabularies*.** A re-publish that leaves every header
byte-identical and changes one cell from `YES` to `Y` passes the header check
completely — and the July-2026 re-publish is standing proof that this Fund edits this
file in place. The value allowlist is the only guard that can see that change.

### M3.4 `geocode_success` asserts something that did not happen

`NMTCMapper.check_tract()` (`mapper.py:141`) sets `geocode_success=True` when no
geocoding was performed at all — the caller supplied the GEOID. It is not a
fabricated *negative*, so it is outside this release's central defect, and setting
it `False` would be worse: `eligibility_status` reads
`if not self.geocode_success: return "geocode-failed"`, so a `False` here would
mislabel every direct tract lookup as a geocode failure.

The field is doing a job its name does not describe: it means "no geocoding step
failed," not "geocoding succeeded." **Remedy: documentation, not a rename.**
Renaming it is a breaking change with no honesty payoff, and 0.5.0 has enough
breakage. The docstring and README should state the semantics, and the field should
be described as "no unresolved address stands between this result and its tract."

### M3.5 Count

**Nine boolean fields swept. Six change.**

- 1 dropped: `is_nmtc_native_area`.
- 1 becomes `Optional[bool]` on every path: `is_opportunity_zone`.
- 4 become `Optional[bool]` on the indeterminate paths only: `is_non_metro`,
  `is_high_migration_rural`, `severe_distress`, `deep_distress`.
- 3 unchanged: `nmtc_eligible` (fixed in 0.4.0), `tract_found`, `geocode_success`
  (documentation only).

The answer is not "only the two we knew about," and it was not provable by reading
comments — fields 2–5 have no comment on them anywhere. It was provable only by
reading the two indeterminate branches next to the field list.

---

## M4 — Rendering: the fabrication survives a type change unless killed explicitly

```python
# eligibility/checker.py:94
print(f"  Opportunity Zone: {'Yes' if self.is_opportunity_zone else 'No'}")
```

`None` is falsy. Change the type and this line still prints `No`. The
human-readable block — the thing a user reads and pastes into a memo — would keep
asserting the fabricated negative after the type was fixed. The
`nmtc-eligibility` skill currently instructs models: *"Do not repeat the
`Opportunity Zone: No` line as fact… narrate it as 'not confirmed as an Opportunity
Zone.'"* **The skill is compensating for the package. 0.5.0 makes that compensation
unnecessary.**

### M4.1 Every site where a boolean is rendered or serialised

Swept exhaustively. The brief named four candidate sites; two of them do not exist.

| # | Site | Booleans surfaced | Falsy-`None` trap? | 0.5.0 action |
|---|---|---|---|---|
| 1 | `EligibilityResult.summary()` — `checker.py:91` | `is_non_metro` | **Yes** (becomes tri-state on Path B) | Three-state render |
| 2 | `EligibilityResult.summary()` — `checker.py:94` | `is_opportunity_zone` | **Yes** — the headline trap | Three-state render |
| 3 | `EligibilityResult.summary()` — `checker.py:95` | `is_high_migration_rural` | **Yes** | Three-state render |
| 4 | `EligibilityResult.eligibility_status` — `checker.py:55, 57` | `geocode_success`, `tract_found` via `not` | No — both stay `bool` | None; add a regression test pinning that they stay `bool` |
| 5 | `enrich_dataframe()` — `checker.py:168-199` | writes `is_non_metro`, `is_high_migration_rural`, `is_nmtc_native_area`, `severe_distress`, `deep_distress` into an object-dtype frame | `None` stores correctly; **`is_nmtc_native_area` must leave the column list** | Drop one column; document the tri-state columns |
| 6 | `check_tract()` public dict — `checker.py:135-147` | all six | Consumers unwrap it themselves | Values follow the field contract |
| 7 | `EligibilityResult` dataclass `__repr__` (auto-generated) | all | No — prints `None` faithfully | None |
| 8 | `NMTCMapper.eligible_count()` — `mapper.py:220-229` | none (counts only) | No | None |
| 9 | README "Output Columns", `examples/nmtc_eligibility_demo.ipynb`, skill worked examples | all | Documentation | Rewrite (§M8, §M9) |

**`EligibilityResult.to_dict()` does not exist.** **There is no CLI** — no
`[project.scripts]`, no `console_scripts`, no `__main__`. Both were named in the
brief; neither is a site. And `summary()` renders only three of the nine booleans:
`severe_distress`, `deep_distress`, `tract_found`, `geocode_success` and
`is_nmtc_native_area` are never printed at all.

**`is_opportunity_zone` is absent from `enrich()` output entirely.** The batch path
produces **ten** eligibility columns plus `eligibility_status` — **eleven** in total,
not "eleven plus `eligibility_status`"; the `eligibility_cols` list in
`enrich_dataframe()` holds exactly ten names and `eligibility_status` is assigned
separately a few lines below it. OZ status is not among them (confirmed against the demo notebook's exported column list). Single-address
callers get an OZ answer; batch callers cannot. 0.5.0 should **not** close that gap
— adding columns is a data-surface change, not an honesty fix, and this release's
invariant surface must stay small — but the README's Output Columns table must stop
implying the batch path is complete, and must list all columns actually written
(it currently omits `is_high_migration_rural` and `is_nmtc_native_area`).

### M4.2 The rendering specification

Three states, three renderings, on the eligibility-line pattern 0.4.0 established:
the qualifier is **inline on the same line**, never a footer, because a footer is
what gets dropped when a user copies one line into a memo.

```
  Opportunity Zone: ✅ YES — GEOID is on the Dec-2018 designation list, which is
                    2010-tract-based (a claim about the list, not about the parcel)
  Opportunity Zone: ❓ NOT CONFIRMED — not on the 2018 designation list, which is
                    2010-tract-based (indeterminate, NOT "not an Opportunity Zone")
  Opportunity Zone: ❓ UNKNOWN — no census tract resolved
```

The middle line is the 78,039-tract case and the one that matters. It must not
contain the word "no" as a verdict. The third line is the geocode-failure branch.

**The `True` line carries a qualifier too, and this section did not give it one.**
That was the document applying its own principle asymmetrically: the indeterminate
line got a full inline explanation while the `True` line shipped bare as
`✅ YES — designated 2018 QOZ`. §M1.3 already measured why a bare `YES` is not good
enough — **527 of the 7,356 `True`s (7.2%)** are 2020 tracts drawing under 99% of
their land from the same-numbered 2010 tract, and the worst, `42063961102`, draws
**12.4%**; an address in the other 87.6% gets a `True` for a designation that does not
cover the ground it stands on. If the reason a footer is unacceptable for the `None`
state is that users paste a single line into a memo, that reason applies unchanged to
the `True` state — whose line is *more* likely to be pasted, because it is the one
that helps the deal. The qualifier is inline for all three states.

Same three-state treatment, same inline-qualifier pattern, for `Non-Metro:` and
`High Migration:` when they are `None`:

```
  Non-Metro:        ❓ UNKNOWN — tract not read
  High Migration:   ❓ UNKNOWN — tract not read
```

And the implementation rule for the build, which is the actual defect here:
**every one of these is a three-branch `if`, never a ternary on the value.** A
`'Yes' if x else 'No'` anywhere in 0.5.0's `summary()` is a bug, and the build
should add a test that greps the rendered output of an indeterminate result for the
strings `": No"` and `"Yes"` and fails on either.

---

## M5 — The silent-degradation problem this release creates

`bool → Optional[bool]` is a breaking change that does not break loudly:

```python
if result.is_opportunity_zone:            # still runs; None is falsy; now means something else
if result.is_opportunity_zone is False:   # silently stops matching — 0 rows, forever
```

A user's code keeps working and starts meaning something different. That is
precisely the class of defect this package exists to close, introduced by the fix
for it. It cannot be avoided — the alternative is keeping the fabrication — so it
has to be made impossible to miss.

### M5.1 The parallel property

0.4.0 solved this for the verdict with `eligibility_status`, a four-way string that
makes the indeterminate case impossible to miss. **`is_opportunity_zone` gets the
same treatment: `opportunity_zone_status`, a read-only property, three values.**

| `is_opportunity_zone` | `opportunity_zone_status` | Meaning |
|---|---|---|
| `True` | `"designated"` | The GEOID appears on the CDFI Fund's Dec-2018 designation list |
| `None` (tract in hand) | `"not-confirmed"` | Not on the 2018 list — not-designated, a 2010→2020 vintage miss, or an Island Area outside this table. Not distinguishable, and not a "no" |
| `None` (no tract) | `"no-tract"` | Geocoding returned no match; there is nothing to test membership against |

Three values, not four: the reasons behind `not-confirmed` are exactly what the
package cannot distinguish, so enumerating them as separate statuses would
re-introduce the fabrication in string form.

`"not-confirmed"` is chosen deliberately to match the skill's existing required
narration ("not confirmed as an Opportunity Zone"), so the skill's rule becomes a
direct read of a field rather than a re-write of a rendered line.

**`summary()` leans on it.** The rendering in §M4.2 is a switch on
`opportunity_zone_status`, not on the truthiness of `is_opportunity_zone` — which
structurally prevents the ternary trap from coming back.

The four Path-B tri-states (§M3.2) do **not** get individual status properties.
They are already covered: `eligibility_status ∈ {not-found, geocode-failed}` is
exactly the condition under which they are `None`, and adding four more string
properties would be noise. The README must state that relationship explicitly.

### M5.2 The upgrade table

Modelled on `hmda-analyzer` 0.6.0's "UPGRADING FROM 0.5.0 — READ THIS FIRST". This
table goes at the top of the 0.5.0 CHANGELOG entry, above the Added/Changed/Fixed
sections, not below them.

**Silent — code keeps running, meaning changes:**

| Call shape | Did | Does | Write instead |
|---|---|---|---|
| `if r.is_opportunity_zone:` | True for 7,356 tracts | Same rows | Safe. Still means "designated" |
| `if not r.is_opportunity_zone:` | "not an OZ" | "not confirmed" — 78,039 tracts | `if r.opportunity_zone_status == "not-confirmed":` |
| `r.is_opportunity_zone is False` | matched 78,039 tracts | **matches nothing** | `r.opportunity_zone_status != "designated"` |
| `str(r.is_opportunity_zone)` | `"False"` | `"None"` | `r.opportunity_zone_status` |
| `df["is_non_metro"] == False` (after `.enrich()`) | matched metro **and** unresolved rows | matches only rows actually read as `Metro` | Intended. To restore the old set: `df["is_non_metro"] != True` |
| `df[~df["severe_distress"]]` | included indeterminate rows as "not severe" | `~None` on object dtype → `TypeError` | `df["severe_distress"] != True` |
| `bool(r.severe_distress)` on an absent tract | `False` | `False` (from `None`) — same value, different meaning | Check `r.eligibility_status` first |

**Loud — code raises, which is the good case:**

| Call shape | New behaviour |
|---|---|
| `r.is_nmtc_native_area` | `AttributeError` |
| `EligibilityResult(..., is_nmtc_native_area=False)` | `TypeError: unexpected keyword argument` |
| `df["is_nmtc_native_area"]` after `.enrich()` | `KeyError` |
| `sum(r.is_opportunity_zone for r in results)` | `TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'` |
| `int(r.is_opportunity_zone)` | `TypeError` |
| `assert isinstance(r.is_opportunity_zone, bool)` | `AssertionError` — **this is `tests/test_mapper.py:66` today**, and it is the in-repo tripwire the build must update |

**Not changing** (state it, so nobody upgrades defensively against it):
`nmtc_eligible`, `eligibility_status`, `distress_level`, `tract_found`,
`geocode_success`, all three metrics, `distress_description`, `data_source`,
`tract_count`, `oz_tract_count`, `eligible_tract_count`, and every eligibility
number in §M7.

---

## M6 — `_compute_eligibility()`: blast radius, established by execution

Three structural defects were deferred out of the 0.4.2 hotfix. The 0.4.2 audit
reported that `_compute_eligibility()` backs only `load_sample_table()` /
`from_sample()`. **That was a relayed claim and had never been re-verified.** It
was verified here by execution, not by reading.

### M6.1 The trace

`nmtcmapper.data.loader._compute_eligibility` and `_process_eligibility_table` were
wrapped with call-stack recorders, then four paths were exercised against the real
cached 4.8 MB workbook:

| Path exercised | `_compute_eligibility` entered? |
|---|---|
| `load_eligibility_table()` — live `.xlsb`, 85,395 rows | **No** (0 calls) |
| `load_eligibility_table()` again — cache re-read / re-validate | **No** (0 calls) |
| `NMTCMapper.from_sample()` | Yes — via `load_sample_table@loader.py:523` |
| `load_sample_table()` | Yes — via `loader.py:523` |

**It is sample-only.** Confirmed, not relayed.

The reason is structural rather than incidental, which is what makes it durable:
`_process_eligibility_table()` is reached only from `_load_eligibility_table()`'s
`else` branch at `loader.py:275`, which requires `path.suffix != ".xlsb"`. `path`
comes only from `download_eligibility_file()`, which returns only
`_eligibility_cache_path()`, which is `CACHE_DIR / ELIGIBILITY_CACHE_FILENAME` with
`ELIGIBILITY_CACHE_FILENAME = "NMTC_LIC_Eligibility_2016_2020.xlsb"` — a module
constant. **`_process_eligibility_table()` is unreachable dead code**, along with
`ELIGIBILITY_FILE_COLUMNS`, the `state`/`county`/`tract` GEOID assembly, and the
`"NATIVE_AREA"` mapping that is the only thing in the package that could ever have
set `is_nmtc_native_area=True`.

**The priority order does not change. The OZ work leads 0.5.0.** But three
qualifications:

1. **`load_sample_table` is in `__all__`.** Sample-only is not private. The wrong
   rule is exported, importable, and reachable from a documented constructor.
2. **A wrong rule in a demo teaches the wrong rule.** The sample table is what the
   README, the notebook, and the offline tests exercise. It is the version of NMTC
   eligibility a reader learns from.
3. **The dead branch should go.** The "22 lines" this document first attributed to
   deleting `_process_eligibility_table` **and** `ELIGIBILITY_FILE_COLUMNS` is the
   size of the function alone: `loader.py:424-445`, `def` through `return df`,
   counted this session — 22 lines exactly, for the function, not for both. The dict
   is a further **14 lines** (`schema.py:129-142`) under a two-line comment header,
   and removing the pair also takes the import at `loader.py:20`, the `else`-branch
   call site at `loader.py:275-276`, and a back-reference in the comment at
   `schema.py:167`. That is roughly forty lines across two modules; the exact figure
   is the build's to state after the edit, not this document's to predict. The line
   count was never the argument. The argument is that the mapping misleads
   maintainers about where `is_nmtc_native_area` could come from — directly relevant
   to §M2 — and that removing it is not a behaviour change, because nothing reaches
   it.

### M6.2 How wrong the rule is, measured

Applying `_compute_eligibility()`'s rule to the live 85,395 rows and comparing to
the Fund's published flags:

| Flag | Rule computes `True` | Fund publishes `True` | Disagreements |
|---|---|---|---|
| `nmtc_eligible` | 36,267 | 35,335 | **932** |
| `severe_distress` | 26,420 | 21,182 | **5,238** |
| `deep_distress` | 8,828 | 8,061 | **767** |
| `distress_level` | — | — | **6,049** |

Every disagreement is over-inclusive. The rule invents eligibility.

### M6.3 The correct rule for each of the three, with citations

**(1) Severe and deep distress must be AND-ed with LIC.**

Authority, most direct first: the workbook's own column headers, which the loader
already pins — column 14 reads *"Severe distress=**LIC AND** (Poverty>30%;
MFI<=60%;Unemployment>=1.5)"* and column 15 *"Deep distress=**LIC AND**
(Poverty>40%; MFI<=40%;Unemployment>=2.5)"*. Structurally: these are CDFI Fund
*Areas of Higher / Deep Distress* criteria, which the Allocation Agreement applies
to QLICIs, and a QLICI is by definition in a Low-Income Community under
§45D(e)(1) — distress is a tier *within* eligibility, never a route into it.

Measured: the current rule marks **5,197 non-LIC tracts severely distressed** and
**751 non-LIC tracts deeply distressed**. Adding the conjunction (with (3) below)
takes severe from 5,238 disagreements to **20**, and deep from 767 to **3** — and
those residual 20 and 3 are the known artefact of the July-2026 re-publish widening
column C without recomputing O and P, already documented in `schema.py`.

**One negative search, recorded here so it is not run a third time.** Neither
**26 U.S.C. §45D** nor **Treas. Reg. §1.45D-1** contains the term "distress" in any
form: **0 occurrences in each**, counted this session over the full text of both
(`uscode.house.gov`, title 26 §45D, prelim edition; eCFR title 26 §1.45D-1, current),
against **21** occurrences of "low-income community" in the statute and **153** in the
regulation. "Severe distress" and "deep distress" are therefore **not statutory
categories at all** — they are CDFI Fund allocation-agreement commitment categories,
defined by the Fund in its Application and Compliance FAQ and published by the Fund in
columns O and P. That is what makes fitting these two rules to the Fund's published
columns the *correct* method rather than a convenience: there is no statutory text to
fit them to, and the Fund's column **is** the definition. It also explains the shape of
the authority list above — column headers first, FAQ second, statute nowhere — which
would otherwise look like citing the weakest source first.

**(2) The 85% band belongs to high-migration-rural *inside* non-metro — not to
non-metro, and not to high-migration-rural at large.**

```python
ami_lic = (non_metro & (ami <= 0.85)) | (~non_metro & (ami <= 0.80))   # wrong
```

26 U.S.C. §45D(e)(1)(B) sets the income test at **80%** for every tract; what
metro/non-metro status changes is the *benchmark* (statewide MFI for a non-metro
tract; the greater of statewide or metro-area MFI for a metro tract) — and the
workbook has already applied that benchmark, since column 5 is "Census Tract
Percent of **Benchmarked** Median Family Income." The **85%** figure comes from
one place only: **§45D(e)(5)**, added by section 223 of the American Jobs Creation
Act of 2004 (P.L. 108-357).

Read §45D(e)(5) against the paragraph it amends. Verbatim from the U.S. Code
(`uscode.house.gov`, title 26 §45D, prelim edition, fetched and counted this
session):

> **(e)(1)(B)(i)** "in the case of a tract **not located within a metropolitan
> area**, the median family income for such tract does not exceed 80 percent of
> statewide median family income, or"
>
> **(e)(1)(B)(ii)** "in the case of a tract **located within a metropolitan area**,
> the median family income for such tract does not exceed 80 percent of the greater
> of statewide median family income or the metropolitan area median family income."
>
> **(e)(5)(A)** "In the case of a population census tract located within a high
> migration rural county, **paragraph (1)(B)(i)** shall be applied by substituting
> '85 percent' for '80 percent'."
>
> **(e)(5)(B)** "…the term 'high migration rural county' means any county which,
> during the 20-year period ending with the year in which the most recent census was
> conducted, has a net out-migration of inhabitants from the county of at least 10
> percent of the population of the county at the beginning of such period."

The substitution is attached to **(1)(B)(i)** — the non-metropolitan branch — and to
nothing else. And §45D(e)(5)(B) contains **no rurality test and no metropolitan
test**: it is a bare out-migration threshold, so the word "rural" in the statutory
label carries no definitional weight. A metropolitan county can therefore satisfy the
definition of "high migration rural county"; when it does, (1)(B)(i) does not apply to
its tracts at all — they are governed by (1)(B)(ii) — so the substitution has nothing
to operate on. The 85% band reaches a tract only if it is **both**
high-migration-rural **and** non-metropolitan. Non-metro is separately a far larger
set: 13,841 tracts are non-metro; only 1,422 are high-migration-rural.

```python
ami_lic = (ami <= 0.80) | (high_migration_rural & ~metro & (ami <= 0.85))  # correct
```

Measured: the shipped rule grants LIC to **932 tracts on the strength of non-metro
status alone**. The corrected rule reproduces the Fund's published column C
**exactly — 0 disagreements across all 85,395 rows.**

**What that zero does and does not establish.** It is the strongest empirical result
in this document, and it is *silent on the conjunct just restored.* Both
formulations — with `~metro` and without it — score 0 disagreements, because the
population that could tell them apart is empty. Re-derived this session, directly
from the workbook's columns 1 and 13:

| Discriminating population | Count |
|---|---|
| High-migration-rural tracts (column 13 = `YES`) | 1,422 |
| …of which **metropolitan** (column 1 = `Metro`) | **0** |
| …of which non-metropolitan | 1,422 |
| Tracts reaching LIC through the 85% band alone (the 168) | 168 |
| …of which **metropolitan** | **0** |
| Symmetric difference of the two rules over all 85,395 rows | **0** |

The 168 are the tracts column C absorbed in the July-2026 re-publish; every one of
them is non-metro, with benchmarked MFI between **80.02%** and **84.99%** — squarely
inside the band and outside the 80% test. So the zero is strong evidence for exactly
two propositions: that the split is 80/85 rather than 85/80, and that the 85% band is
restricted to high-migration-rural rather than to non-metro. It is evidence for
nothing about the non-metropolitan conjunct, because no row on this file exercises it.

The conjunct is therefore **redundant on the current file as an empirical property,
not as a logical one** — and the distinction is the whole point. 1,422 of 1,422 HMR
tracts being non-metro is a fact about one published file, of exactly the kind this
Fund has already changed once at the same URL without renaming it. Restoring the
conjunct is a **documentation correction with a verified zero-row behaviour delta**,
not a behaviour change: §M7's invariants are unmoved, and the build can assert that
directly (the two rules must agree on all 85,395 rows, and the count of metro HMR
tracts must be 0 — a test that will fail loudly the day the Fund publishes one).

One sentence on why this was missed, because it is the lesson of the release rather
than a footnote to it. The shipped rule's defect was that it **conflated non-metro
with high-migration-rural**; the first correction over-corrected by removing non-metro
from the band **entirely**. A correction can be wrong in the same direction as the
defect it corrects — over-inclusive — which is the direction this whole release exists
to close.

**(3) `>=` vs `>` — correct for LIC, wrong for severe and deep.**

The brief says all three prongs are over-inclusive on `>=`. Two are; the LIC prong
is not. §45D(e)(1)(A) requires a poverty rate "**of at least** 20 percent," so
`pr >= 0.20` is right and must not be changed. The distress prongs are strictly
greater: the column headers read `Poverty>30%` and `Poverty>40%`, and the April
2025 Compliance FAQ Q32 states the deep criterion as "census tracts with poverty
rates **greater than** 40%."

Settled empirically rather than by reading, because the boundary population is
non-trivial — 83 LIC tracts sit at exactly 30.0% poverty and 29 at exactly 40.0%.
Of the LIC tracts at exactly 30.0% that qualify on the poverty prong alone
(21 tracts), the Fund published `severe = NO` for **all 21**. Of those at exactly
40.0% qualifying on poverty alone (**13** tracts), the Fund published `deep = NO` for
**all 13**. Disagreement totals confirm it and pin both counts: with `>` the corrected
rules disagree on 20 severe / 3 deep; with `>=`, on 41 / 16. The differences —
41 − 20 = **21** and 16 − 3 = **13** — *are* the two discriminating populations, and
that arithmetic is what caught the earlier figure of 12: a count the document's own
downstream numbers contradicted.

The thirteenth is `22071980000` — poverty exactly 40.0%, MFI `NA`, unemployment ratio
0.0, Fund publishes `deep = NO`. An earlier pass dropped it on the grounds that
"qualifies on the poverty prong alone" cannot be established when MFI is null. That
exclusion is not principled. The two hypotheses make **opposite** predictions on the
row — `>=` says deep, `>` says not-deep — and the Fund published `NO`, so it
discriminates exactly as the other twelve do; a null MFI cannot fire the MFI prong
under either formulation, which is precisely why the row is decided by the poverty
prong alone. **13/13, not 12/12.** The conclusion is unchanged — `>` is correct for
both distress prongs — but a figure its own downstream numbers contradict is not.

| Prong | Current | Correct | Authority |
|---|---|---|---|
| LIC poverty | `>= 0.20` | `>= 0.20` (unchanged) | §45D(e)(1)(A), "at least 20 percent" |
| LIC income | `non_metro ? <= 0.85 : <= 0.80` | `<= 0.80`, plus `hmr & ~metro & <= 0.85` | §45D(e)(1)(B)(i)-(ii); §45D(e)(5)(A) |
| Severe poverty | `>= 0.30` | `> 0.30`, AND LIC | Column-14 header; 21/21 empirical |
| Severe income / unemployment | `<= 0.60` / `>= 1.5×` | unchanged, AND LIC | Column-14 header |
| Deep poverty | `>= 0.40` | `> 0.40`, AND LIC | Column-15 header; FAQ Q32; 13/13 empirical |
| Deep income / unemployment | `<= 0.40` / `>= 2.5×` | unchanged, AND LIC | Column-15 header; FAQ Q32 |

**The sample table's own values move when this is fixed**, since
`load_sample_table()` runs the rule on its 12 synthetic tracts. That is a
deliberate, documented change to demo data — it is not an eligibility number, and
§M7's invariants are untouched by it. The build must re-derive and pin the sample
table's expected values rather than assume they hold.

---

## M7 — Regression invariants

0.5.0 is an honesty and API release, not a data release. **Nothing here may change
who is eligible.** All verified this session against the live cached workbook;
to be verified again by the build and again by the audit.

| Invariant | Value |
|---|---|
| `tracts` | **85,395** |
| `eligible` | **35,335** |
| `distress` | `{ineligible: 50060, lic: 14153, severe: 13121, deep: 8061}` |
| `01013953500` | `nmtc_eligible=True` · `is_high_migration_rural=True` · `distress_level='lic'` |
| OZ set size | **8,764** |
| OZ GEOIDs matching the table (→ `is_opportunity_zone=True`) | **7,356** |

Also invariant, and out of scope for this release:

- the 0.4.2 verdict logic — column C **or** column N;
- the exact-header validation (`ELIGIBILITY_XLSB_EXPECTED_HEADERS`, all nine bound
  indices) and the 16-column count;
- the `nmtc_eligible` tri-state and `eligibility_status`'s four values;
- `NATIONAL_UNEMPLOYMENT_RATE = 0.054` and the six distress constants;
- the value-bounds guard and `ELIGIBILITY_MIN_ROWS`.

If any of those must move, that is a separate release.

One invariant is *added* by this document and should be pinned by a test, because
it is what §M1.4's headline rests on: **7,356 `True` + 78,039 `None` = 85,395, and
`is_opportunity_zone is False` occurs zero times, on every path.**

---

## M8 — The twelve docs-check entries, sorted by what they actually are

### M8.1 They are one kind of thing, and the brief's third category is not among them

The gate was run (`python tools/docs_check.py --allow-source`): **PASS with 12
known failures**. All twelve are `readme-missing-symbol` — assertion-6 findings,
`__all__` exports the README never names. Sorted:

| Group | Count | Entries |
|---|---|---|
| **A — core public API the README never names** | 3 | `EligibilityResult`, `load_eligibility_table`, `geocode_address` |
| **B — exception leaves reached only by a `*DownloadError` / `*ParseError` glob** | 4 | `EligibilityDownloadError`, `EligibilityParseError`, `OZDownloadError`, `OZParseError` |
| **C — exception leaves no glob even reaches** | 5 | `EligibilitySchemaError`, `EligibilityValueError`, `GeocoderError`, `GeocoderTransportError`, `AmbiguousAddressError` |

**All twelve are documentation-only.** None requires a code decision. The brief's
second category — "claims about behaviour that are false" — has **zero** members in
the ledger. That is not because no such claims exist; it is because the gate
**structurally cannot see them**, as `docs-check.toml` itself says under "IT DOES
NOT ASSERT": *"PROSE CLAIMS … no assertion re-derives any number or behaviour stated
in prose. They are checked by a human or not at all."*

So the false-behaviour claims are a **thirteenth-and-beyond** class that lives
outside the ledger, and 0.5.0 owns them anyway. §M8.3 enumerates the ones found.

### M8.2 The fix for Groups B and C: a documented hierarchy, not prose

Nine of the twelve are exception leaves. The README's line 88-90 draws the
hierarchy as a glob — `NMTCMapperError → EligibilityDataError / OZDataError →
specific *DownloadError / *ParseError leaves` — and a reader cannot type a glob
into an `except` clause. Prose that names nine classes in a sentence would satisfy
assertion 6 and remain unreadable.

**Decision: ship the tree.** `nmtcmapper/exceptions.py` already carries the exact
ASCII hierarchy in its module docstring; the README gets that block verbatim, with
a one-line "raised when" beside each leaf. One diagram documents all nine, matches
the source it came from, and gives a reader the `except` clause they need.

The docs-check gate cannot verify the *shape* of a hierarchy (its own limitations
section says so), so **the build should add `tests/test_constraints.py` coverage
asserting the parent of every exception class** — the README's diagram then has a
test behind it, and the gate's blind spot is closed by the suite instead of being
documented as permanent.

All twelve ledger entries are removed in 0.5.0. The gate fails if any is documented
and its entry is not removed, so the removal is not optional bookkeeping.

### M8.3 The false-behaviour claims the gate cannot see

Found by reading the README against the source. Each needs a decision, not a
proofread.

**(a) "pass 10,000 addresses and get results in seconds" (README:22) — the batch
abort.** `_batch_geocode_async` calls `asyncio.gather` **without**
`return_exceptions`, so the first transport failure or ambiguous address in any
chunk aborts the entire batch (`census.py:188`). At 10,000 addresses that is close
to certain. The claim is conditionally true and reads as unconditional.

**Decision: fix the sentence in 0.5.0; fix the behaviour in 0.6.0.** Reasons: the
whole-batch abort is a *deliberate* 0.4.0 correctness decision — its own docstring
says "the previous silent per-row `None` became a fabricated 'ineligible'
downstream, and losing time is strictly better than losing truth" — so reverting it
casually would re-open the defect this package exists to close. Per-row failure
capture needs a designed contract (a `geocode_error` column? a partial-result
object? how `eligibility_status` reports a row that failed transport rather than
no-matching?), and that design does not belong in a release already breaking the OZ
contract. 0.5.0 states the abort semantics plainly next to the capability claim.

The same docstring carries a stale promise — *"Per-row failure capture is planned
for 0.4.1"* — which 0.4.1 and 0.4.2 both shipped without. **0.5.0 corrects it to
0.6.0 or deletes the forward-looking sentence**; a version promise that has already
passed is itself a false claim.

**(b) The README states the wrong distress criteria — and the fix has moved to a
0.4.3 release.** README:141-143 gets **four** values wrong. It reads *"poverty >= 40%
/ MFI <= **50%** AMI / unemployment >= **2x** national (deep)"* where 0.4.2 corrected
the constants to **MFI <= 40%** and **2.5×** against the workbook's own column-15
header and NOTES sheet; and it states **both** poverty prongs as `>=` (*"poverty >=
30%"*, *"poverty >= 40%"*) where the Fund publishes strictly greater — the column
headers read `Poverty>30%` and `Poverty>40%`, and April 2025 Compliance FAQ Q32 states
the deep criterion as *"census tracts with poverty rates **greater than** 40%"* and
independently confirms *"a median family income that does not exceed **40%**"* and
*"unemployment rates at least **2.5 times** the national average."* 0.4.2 fixed
`schema.py` and the CHANGELOG and left the README asserting the superseded values.
This was the twenty-third finding when this document was written, and it is still the
most serious documentation defect in the repository: a user reading the README learns
the wrong federal criterion, and no gate can catch a prose claim.

**It is no longer 0.5.0's to specify.** A **0.4.3 documentation-accuracy release** is
being authored in parallel and takes all of it: the four wrong distress values, the
Native Areas *Higher* → *Deep* Distress mis-categorisation (item (e) below), and the
Island Areas framing. This document must not specify that work a second time — two
releases editing the same README lines from two different decision documents is
exactly how a superseded number gets reintroduced by the later one.

**So this item becomes a verification step, and it gates the 0.5.0 build.** Before
0.5.0 touches the README at all, the build session must confirm that 0.4.3's
corrections are **present on `main`** — not merely authored, not merely committed on a
branch. At the time of writing they are **not**: the branch `fix/0.4.3-docs-accuracy`
exists and sits at `1485923`, the same commit as `main` and as the annotated tag
`v0.4.2`, with **zero commits of its own**, and README:141-143 still carries the
superseded values. The check is concrete and cheap: `git log main --oneline` shows the
0.4.3 commits, and a grep of `main`'s README finds `MFI <= 40%` and `2.5x` and finds no
`MFI <= 50%` or `>= 2x`. If that check fails, 0.5.0's README work waits — because the
0.5.0 rewrite of the Output Columns table and the Known Issues section would otherwise
be written on top of, and would silently re-assert, the wrong criteria.

**(c) "`_compute_eligibility` exists only for the generic CSV path and the built-in
synthetic sample" (README:144).** There is no generic CSV path — §M6 proves the
`.xlsx`/`_process_eligibility_table` branch is unreachable. Fix to "the built-in
synthetic sample only," or delete the clause with the dead branch.

**(d) The Output Columns table is incomplete.** It lists nine columns;
`enrich_dataframe()` writes **ten** eligibility columns plus `eligibility_status` —
**eleven** in total, not "eleven plus `eligibility_status`". Missing from the README:
`is_high_migration_rural` and `is_nmtc_native_area` (the latter is being dropped, so
the correction and the drop land together), which is what makes the arithmetic close:
nine listed + two missing = eleven written. The table must also stop implying OZ status
is available from the batch path — it is not (§M4.1). This item is an instruction to
rewrite that table, so the corrected count propagates into the README rather than
staying here.

**(e) Native Areas is categorised as *Areas of Higher Distress*** in README:192,
CHANGELOG 0.4.1, and the skill. Per FAQ Q32 it is enumerated under **Areas of Deep
Distress** (§M2.3). The README and CHANGELOG halves move to **0.4.3** with item (b);
the skill half stays with 0.5.0 and is specified at §M9.2 (the 268-272 row). 0.5.0
**verifies** the first two on `main` rather than performing them.

**(f) Two stale "114 tests" references in `docs-check.toml`**, not one.
`docs-check.toml:120` claims *"assertion 3 — the '114 tests' claim matches
collection."* The README says 140 and collection is 140, so the comment describes a
prior state. `docs-check.toml:33` carries the same stale number in a different role —
*"Matches a line like '114 tests across all modules …'"* — where it is a worked
*example* for the `claim_pattern` regex rather than an assertion of fact. Both move to
140: the line-120 comment because it is a claim about a gate's result, and those are
the ones that must be true; the line-33 example because a maintainer reading it learns
a number the README has not carried for two releases. Neither is a behaviour change,
and `claim_pattern` itself (`'^(\d+)\s+tests\b'`) is correct and does not move.

### M8.4 `eligible_count` vs `eligible_tract_count`

The brief calls this a naming smell where "one should go." **Neither should go —
they are different things**, and deleting either would remove functionality:

- `NMTCMapper.eligible_count(df)` — a **method** taking a user DataFrame, returning
  a dict of eight summary figures (`total`, `nmtc_eligible`, `pct_eligible`, the
  three distress counts, `ineligible`, `indeterminate`) and printing a block.
- `NMTCMapper.eligible_tract_count` — a **property** with no arguments, returning
  one integer: how many of the 85,395 loaded tracts are eligible.

The real defect is that `eligible_count` does not return a count. It returns a
summary, and its name promises the thing the *other* member actually is.

**Decision: rename `eligible_count` → `summarize_eligibility`, keep
`eligible_count` as an alias emitting `DeprecationWarning`, remove the alias in
0.6.0.** With the alias this is not a breaking change, so it costs nothing to do it
in the release that is already touching the API; deferring it means a second
deprecation cycle later. `eligible_tract_count` keeps its name — it is accurate.
Both names appear in the README rewrite, adjacent, with the distinction stated.

---

## M9 — Sync spec for `cdfi-superpowers`

The drift rule has been discovered late twice. This specifies it at methodology
time. Target: `cdfi-superpowers` at `2026.7.6` (commit `4705124`).

### M9.1 Pin sites — four files, six line-sites

The brief says four **files**, and four is right; what it undercounts is *line-sites*.
Verified against `cdfi-superpowers` at `4705124`: the `>=0.4.2` pin appears at **six**
line-sites across **four** files — `skills/nmtc-eligibility/SKILL.md` (lines 39 and
42), `README.md` (lines 27 and 33), `llms.txt` (line 16), and
`references/package-index.md` (line 13) — plus two plugin-manifest CalVer entries,
which are not the pin. The table below has five rows because it splits `SKILL.md`'s two
sites onto separate rows and merges `README.md`'s two onto one. Every site it names
exists; only the "five files" label was wrong:

| File | Current | Becomes |
|---|---|---|
| `skills/nmtc-eligibility/SKILL.md:39` | `pip install "nmtc-mapper>=0.4.2" nmtc-screener` | `>=0.5.0` |
| `skills/nmtc-eligibility/SKILL.md:42` | "Verified this session (PyPI): **nmtc-mapper 0.4.2**" | `0.5.0`, re-verified against PyPI on the sync date |
| `README.md:27, 33` | `nmtc-mapper >=0.4.2` (table + the load-bearing-floor note) | `>=0.5.0`, with the new floor's reason |
| `llms.txt:16` | `Backed by nmtc-mapper >=0.4.2` | `>=0.5.0` |
| `references/package-index.md:13` | `>=0.4.2` | `>=0.5.0` |
| `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (×2 entries) | `2026.7.6` | next CalVer |

The floor's justification changes with it. `>=0.4.2` is load-bearing because 0.4.2
stopped reporting 168 statutorily-eligible tracts as ineligible. **`>=0.5.0` is
load-bearing because below it `is_opportunity_zone` returns a confident `False` for
78,039 tracts** — the same defect class, one field over, and the skill currently
compensates for it in prose.

### M9.2 Passage-by-passage changes to `SKILL.md`

| Lines | Currently | Becomes |
|---|---|---|
| **245-254** — the `EligibilityResult` field list | Names `is_nmtc_native_area` with the "**always `False`** — see note" caveat | **Remove the field from the list.** Add `opportunity_zone_status` to the Properties sentence alongside `distress_description` and `eligibility_status`. Mark `is_non_metro`, `is_high_migration_rural`, `severe_distress`, `deep_distress` as `Optional[bool]` |
| **268-272** — the `is_nmtc_native_area` paragraph | Explains the field is hardcoded `False` and must not be reported as fact | **Delete entirely.** Replace with one sentence: the field was removed in 0.5.0 because no CDFI Fund tract-keyed source exists; native-area status is a spatial determination against Census AIANNH geographies and is a documented *Areas of Deep Distress* criterion (April 2025 Compliance FAQ Q32) this package does not carry. Route to CIMS |
| **436-451** — the OZ output-presentation rule | "`is_opportunity_zone` is a plain `bool`, so a `False` means EITHER…"; instructs the model to re-narrate a `False`; cites 1,408/16.1% | **The compensation goes; the posture stays.** `is_opportunity_zone` is now `Optional[bool]` and `opportunity_zone_status` says it directly. Rewrite to: report `"designated"` as fact; report `"not-confirmed"` as "not confirmed as an Opportunity Zone" **because the package now says so**, not because the skill is correcting it. Keep the reason (2010-basis designations vs 2020 geocoding) and add the Island Areas third cause |
| **237-243** — "Do not repeat the `Opportunity Zone: No` line as fact" | Compensates for `summary()` printing a bare `No` | **Rewrite.** `summary()` no longer prints `No`; it prints `❓ NOT CONFIRMED …`. The rule becomes "report the line as printed" — which is the point of the release |
| **217-232** — the worked-example `summary()` block for `36005023702` | Shows `Opportunity Zone: No` | **Re-execute against 0.5.0 and paste the actual block.** Expected: `❓ NOT CONFIRMED — …`. Do not hand-edit — the skill's convention is executed output |
| **336-347** — the absent-tract `summary()` block for `36061980000` | Shows `Non-Metro: No`, `Opportunity Zone: No`, `High Migration: No` on a tract the package never read | **Re-execute.** All three become `❓ UNKNOWN — tract not read`. This block is the skill's teaching case for the third state and currently ends with three fabricated negatives underneath the correct `❓ UNKNOWN` verdict |
| **186-200** — the Island Areas scope hole | Correct and already present | **Keep, and cross-reference from the OZ rule** (§M1.2): 75 of the 1,408 unmatched OZ designations are Island Area tracts, not vintage misses |
| **88-115** — the tri-state section | Covers `nmtc_eligible` only | **Extend.** State that `Optional[bool]` is now the package's general contract for any field that can be unobtainable, list the six tri-state fields, and state the rule that ties them together: when `eligibility_status ∈ {not-found, geocode-failed}`, every tract-derived boolean is `None` |
| **537-540** — the NaN rule | "the tract is genuinely `False`/verified-ineligible; only its demographics are null" | **Keep verbatim.** §M3.1(b) re-verified it: the Fund publishes a determination for null-demographic tracts, so `11001980000`'s `False` is a real `NO`. This is the one place a `False` next to nulls is correct, and the skill already says why |

### M9.3 What must not change

The third-state rule (127-149), the hard failure rule (117-125), and the
vintage-scope rule (151-200) are unaffected. 0.5.0 makes the package **conform** to
the third-state rule rather than requiring the skill to enforce it against the
package — the rule's text does not need to move for that to be true.

### M9.4 Sequencing

The skill's convention is executed output, so the sync cannot be written from this
document. Order: 0.5.0 to PyPI → clean-venv install → re-execute every worked
example → paste actual output → bump pins and CalVer in one commit. A skill synced
before the release exists would be asserting output nobody ran.

---

## 10. What the commissioning brief got wrong

Named in advance by the brief: that `_compute_eligibility()` reaches only the
sample path; that `main` is at `1485923`; that M3's field list is complete; that
`summary()` at `checker.py:94` is the only rendering site. Findings, including the
twenty-third:

| # | Claim | Finding |
|---|---|---|
| 1 | `_compute_eligibility()` reaches only the sample path *(flagged as relayed)* | **Confirmed by execution** (§M6.1). Zero calls from two live loads; both calls from `load_sample_table`. The stronger fact the brief did not have: `_process_eligibility_table` is *structurally* unreachable, so it is dead code, not merely unused |
| 2 | `main` is at `1485923` | **Correct**, and it is the commit the annotated tag `v0.4.2` points to (`git rev-parse v0.4.2` returns `2cb163d`, the tag *object*, which is why the SHAs look different). But it is **not a merge** — `1485923` has one parent and the 0.4.2 work landed linearly. The last merge on `main` is `5a4728a` (`chore/docs-check-gate`) |
| 3 | M3's boolean list is complete | **Incomplete in the direction that mattered.** The eight named fields are real, but the defect is not per-field — it is per-*branch*. Both indeterminate branches set six booleans to `False`. Nine fields swept, six change (§M3.5) |
| 4 | `summary()` at `checker.py:94` is the only rendering site | **Three sites in `summary()`, not one** — lines 91, 94, 95 all use the `'Yes' if x else 'No'` ternary and all three fields become tri-state |
| 5 | Sweep `to_dict()` | **`EligibilityResult.to_dict()` does not exist** |
| 6 | "the CLI if there is one" | **There is none** — no `[project.scripts]`, no `console_scripts`, no `__main__` |
| 7 | The twelve docs-check entries "are not one kind of thing" | **They are.** All twelve are `readme-missing-symbol` assertion-6 omissions, all documentation-only (§M8.1) |
| 8 | The "10,000 addresses" claim is one of the twelve | **It is not in the ledger at all.** `docs-check.toml` explicitly excludes prose claims from the gate's scope, so it is a thirteenth item the gate structurally cannot see — which makes it *more* dangerous, not less |
| 9 | `eligible_count` / `eligible_tract_count` — "one should go" | **Neither should.** A method over a user DataFrame and a property over the loaded table (§M8.4). The real defect is that `eligible_count` returns a summary, not a count |
| 10 | "1,408 vintage misses" | **1,408 confirmed, but it is three causes:** 1,332 vintage retirements, **75 Island Area tracts** the Fund's table never covers at any vintage, and 1 GEOID (`51019050100`) invalid at both vintages (§M1.2). The package README asserts one cause for all of them |
| 11 | "A `True` is trustworthy" — stated as settled | **True as a claim about the designation list; qualified as a claim about ground.** 527 of 7,356 matched GEOIDs (7.2%) are 2020 tracts drawing under 99% of their land from the same-numbered 2010 tract; the worst is 12.4% (§M1.3) |
| 12 | The crosswalk exclusion is weaker here than in `hmda-analyzer` | **It is stronger, for a different reason.** Not maintenance — 38.7% of the successor tracts a crosswalk would produce also contain never-designated 2010 territory, so every extra answer would be an inference presented as a legal designation (§M1.5) |
| 13 | Q31 enumerates 11 resources, Native Areas absent | **Verified, from the document's own header.** But **Q32 names "NMTC Native Areas" explicitly** as one of four *Areas of Deep Distress* criteria in the CY 2024-2025 Application, so "no source exists or is coming" overstates it — the correct claim is that the Fund publishes no tract-keyed lookup while treating it as a live compliance category (§M2.3) |
| 14 | Native Areas is an *Areas of Higher Distress* criterion (README, CHANGELOG, skill all say so) | **Mis-categorised.** FAQ Q32 places it under **Areas of Deep Distress** |
| 15 | "all three [`_compute_eligibility` defects] are over-inclusive" | **True, but `>=` vs `>` is correct for LIC.** §45D(e)(1)(A) says "at least 20 percent," so `pr >= 0.20` must not change. Only the severe and deep poverty prongs are wrong (§M6.3) |
| 16 | The 85% band defect described as "`is_non_metro` standing in for the 85% band" | **It is two errors, not one:** non-metro tracts get the wrong *threshold* (85% instead of 80%), and the high-migration-rural restriction is missing. 13,841 non-metro tracts vs 1,422 HMR. The first correction of this then introduced a third error in the same direction — see §10.1, finding 24 |
| 17 | `is_opportunity_zone` becomes `None` "otherwise" | **Needs one carve-out.** `check_tract()` on a retired 2010 GEOID returns `True` with `tract_found=False` — the OZ answer is *more* complete than the eligibility answer there, and a naive "None unless found" would destroy a correct `True` (§M1.4) |
| 18 | The skill pins `nmtc-mapper>=0.4.2` "in four files" | **Four files is correct; six line-sites** — `SKILL.md` ×2, `README.md` ×2, `llms.txt`, `references/package-index.md` — plus two plugin-manifest CalVer entries. This document's own "five files" heading was the error, not the brief's count (§M9.1) |
| 19 | The tri-state fix is the release's user-visible impact at 1,408 tracts | **78,039 tracts change their returned value** — 91.4% of the universe. 1,408 is only the subset where the old `False` was demonstrably wrong (§M1.4) |
| 20 | `severe_distress=False` on a null-demographics tract is suspect | **It is not, on the live path.** The Fund publishes an explicit `NO` for all 2,750 null-demographic rows; the package reads it rather than computing it. The concern is real only on the sample path (§M3.1b) |
| 21 | The eligibility table might omit some 2020 tracts | **It does not.** The Fund's 85,395 rows are exactly the 2020 Census Gazetteer national tract set — zero in either direction. Every one of the 1,408 misses is a GEOID that is not a 2020 tract at all, not a coverage gap (§M1.2) |
| 22 | `is_non_metro` is a safe passthrough | **The parse is a not-equal test** (`!= "METRO"`), so any future third value silently becomes `True`, and the header guard cannot see a vocabulary change (§M3.3) |
| **23** | **— the one to find —** | **The README states the wrong federal deep-distress criteria.** README:141-143 still carries the 0.4.1 values — *"MFI <= 50% AMI / unemployment >= 2x national"* — that 0.4.2 corrected to **40%** and **2.5×** in `schema.py`, against the workbook's own column-15 header. Independently confirmed by FAQ Q32. The hotfix corrected the constants and the CHANGELOG and left the README asserting the superseded numbers, and no gate can catch a prose claim. The package computes one criterion and documents another (§M8.3b) |

Two smaller notes: the brief's framing of the twelve as *"the nine exception-hierarchy
leaves the README reaches only through a `*DownloadError` glob"* conflates Groups B
and C — only **four** are glob-reachable; the other **five** match no glob at all
and are absent from the README in every form. And the brief's "140 tests" is
correct (collection confirms 140), though `docs-check.toml`'s own comment still
describes a "114 tests" claim.

### 10.1 What this document got wrong — findings 24 to 26

The table above is the *brief's* errors. This section records the document's own,
because the same rule applies to it, and because a build reading this file needs to
know which of its claims moved after the hostile audit. Finding 24 is the audit's;
25 and 26 were found while executing its remedy.

| # | Claim as first written | Finding |
|---|---|---|
| **24** | §M6.3(2)'s corrected LIC rule: `ami_lic = (ami <= 0.80) \| (hmr & (ami <= 0.85))` | **It drops a statutory conjunct.** §45D(e)(5)(A) attaches the 85% substitution to paragraph **(1)(B)(i)** — the *non-metropolitan* branch — and §45D(e)(5)(B) defines "high migration rural county" by out-migration alone, with no rurality test and no metropolitan test. A metropolitan county can meet that definition, and its tracts are governed by (1)(B)(ii), which the substitution never touches. `~metro` is restored. Found by the hostile audit **inside the document's single strongest empirical result** — the place a brief instructing the session to hunt for hidden assumptions did not point (§M6.3(2)) |
| **25** | §M6.3(3)'s deep discriminating count: **12** | **It is 13**, and the document's own arithmetic said so — it quoted 3 disagreements under `>` and 16 under `>=`, and 16 − 3 = 13. The omitted tract is `22071980000`, dropped for a null MFI on reasoning that does not survive contact: both hypotheses predict opposite answers for it and the Fund published `NO`, so it discriminates exactly as the other twelve do (§M6.3(3)) |
| **26** | §M1.5(b): "OZ 2.0 designations under OBBBA §70421 are expected in 2027 **on a *newer* basis again**" | **Same basis, different scheme — and the clause was uncited.** Rev. Proc. 2026-14 §3.01(3) fixes OZ 2.0 eligible-tract boundaries to those "established for the 2020 decennial census", the basis this package already uses, while Treasury's rural methodology (S4 fn.10) directs readers to the **2024 TIGER** tract map. OZ 2.0 would therefore *not* obsolete a 2010↔2020 crosswalk, so that half of ground (b) does not hold as written. Ground (a) — the 38.7% mixed-descent measurement — is load-bearing and unaffected (§M1.5b) |

Two of the three are the same failure in different clothes, and it is worth naming
because it is the one this document is structurally prone to: **a number or a clause
carried alongside evidence that does not reach it.** The zero-disagreement fit is real
and reaches the 80/85 split; it does not reach the non-metro conjunct. The 38.7%
measurement is real and reaches the crosswalk exclusion; it does not reach the OZ 2.0
sentence sitting next to it. Adjacency to strong evidence is not support, and both
survived several passes because they were standing next to something true.

---

## 11. What 0.5.0 does not do

Stated so the audit can check the boundary rather than infer it.

- **No crosswalk.** No 2010↔2020 tract conversion ships (§M1.5).
- **No second-vintage geocoding.** Resolving an address at both the 2010 and 2020
  vintages would let the package answer OZ status positively for the 1,332 retired
  designations. It doubles the geocoder call volume, needs its own vintage-binding
  design against `TRACT_VINTAGE`, and is a feature — deferred, and named here so it
  is not mistaken for an oversight.
- **No Island Areas file.** `NMTC_LIC_Territory_2020_December_2023.xlsx` is not
  loaded. The 75 Island Area OZ tracts stay `None`, and the skill keeps routing those
  addresses to CIMS. The deferral stands for 0.5.0, but **the CHANGELOG must name it
  for what it is**: FAQ Q32 item 4 makes *US Island Areas* one of the four Areas of
  Deep Distress criteria (§M1.2), so this is a deferred gap in a **named federal
  criterion**, not a coverage note about a file the package happens not to load. Those
  are different admissions and the smaller one is not the true one.
- **No per-row batch failure capture.** 0.6.0, with a designed contract (§M8.3a).
- **No eligibility number moves.** §M7.
- **No OZ 2.0.** `docs/oz2-methodology.md` is a separate decision document about
  designations that do not yet exist; nothing in it is implemented here.
