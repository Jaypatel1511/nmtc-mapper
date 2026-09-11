# Opportunity Zone 2.0 — methodology for the 0.5.0 restoration

**Status:** decision document. No code, no API signatures, no tests. Written before
implementation, per the portfolio rule for eligibility determinations under a federal
tax credit.

**Scope:** three questions — the answer space for an absence (Q1), the census-tract
GEOID scheme of the source (Q2), and whether a rural flag is a returnable fact (Q3).
Out of scope and untouched: OZ 1.0, `is_nmtc_native_area`, the docs-check ledger, the
geocoder exception branch, the output-columns table, and every part of `oz-tracker`.

---

## 0. Sources actually read

Everything below was fetched live on **2026-08-05** and is pinned by digest. Citations
are to the documents' own headers, not to URL labels or search snippets.

| # | Document | Identifier from the document itself | SHA-256 |
|---|---|---|---|
| S1 | Rev. Proc. 2026-14 | header line `Rev. Proc. 2026-14`; `26 CFR 601.601`, *(Also Part 1, §§ 1400Z-1, 1400Z-2.)*; §6: "This revenue procedure is effective on **April 6, 2026**." | `bf8538c7…d191032` |
| S2 | Appendix to Rev. Proc. 2026-14 | `rp-26-14-appendix.xlsx`; single sheet **`Appendix for Designation RP_cor`**; 25,332 data rows | `5e21ee2f…39c46969` |
| S3 | Treasury OTA, *Eligibility Criteria for Determining Census Tracts Eligible to be Nominated as 2027 Qualified Opportunity Zones under § 70421 of the One, Big, Beautiful Bill Act* | cover: "Department of the Treasury / Office of Tax Analysis / **March 2026**" | `2c9a1a7f…da2c6e30` |
| S4 | Treasury OTA, *Methodology for Determining Census Tracts Eligible to be Nominated as 2027 Qualified Opportunity Zones Comprised Entirely of a Rural Area under § 70421 …* | cover: "Department of the Treasury / Office of Tax Analysis / **March 2026**" | `f42c01c1…a5d85ce8` |
| S5 | Treasury data-transparency tract file | sheet `oz2_for_data_transparency`, 85,529 rows × 12 cols + `Notes` sheet; Notes footer "US Department of the Treasury / March 2026" | `9d41e658…d57e37dc0` |
| S6 | This package's own eligibility table | CDFI Fund `NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb`, sheet `2016-2020`, 85,395 tracts | `3a6f5851…428772d49` |

S3 and S4 are the methodology documents S5's `Notes` sheet names as authoritative for
`eligible_lic` and `rural_status` respectively.

Reused rather than re-derived: **`hmda-analyzer` 0.6.0,
`hmdaanalyzer/methodology/tract_vintage_methodology.md`** — §M1.2a (scheme vs. basis)
and §M5 (no crosswalk). Both are cited, not restated.

---

## 1. A framing correction that precedes all three questions

The commissioning brief asks whether the Appendix is "an exhaustive list of **designated**
tracts," and proposes a flag named `is_oz2_designated`. **No tract has been designated.
The Appendix does not list designations and was never going to.**

S1 §1 (Purpose), verbatim:

> This revenue procedure provides guidance to the Chief Executive Officer (CEO) of any
> State, of any territory of the United States, and of the District of Columbia regarding
> the procedure for **nominating** population census tracts to be designated as qualified
> opportunity zones (QOZs) effective on January 1, 2027 …

S1 §3.01(1), verbatim:

> … the Treasury Department and the IRS have identified 25,332 population census tracts
> that are LICs **eligible for nomination** as a 2027 QOZ. … A list of population census
> tracts **eligible for nomination** as a 2027 QOZ, including those comprised entirely of
> a rural area, is provided in the Appendix to this revenue procedure.

The statutory sequence, from S1 §2.02(e)–(f):

> … the term "determination period" means the 90-day period beginning on the decennial
> determination date (including any extension), the first decennial determination date
> being **July 1, 2026**.

> … the State CEO may request, and receive, a 30-day extension of this deadline, which
> would conclude, at the latest, on **October 28, 2026**.

> … the 30-day consideration period … would conclude on **November 27, 2026**, at the
> latest. Under § 1400Z-1(b)(2), however, the State CEO may request, and receive, a 30-day
> extension of this deadline, which would extend it to **December 28, 2026**, at the latest.

As of the date of this document (**2026-08-05**) the nomination window has been open for
36 days and closes no earlier than 2026-09-29. Certification by the Secretary cannot occur
before it closes. There is therefore **no designation data source in existence**, correct or
otherwise, and none can exist before late 2026.

**Decision.** `is_oz2_designated` is not proposed and must not ship in 0.5.0 under any
answer space, including all-`None`. A tri-state flag named `…_designated` that can only
ever return `None` is not conservative — it is a claim that a designation determination
was attempted. Nothing was attempted, because nothing exists to attempt it against.
The restoration is of **OZ 2.0 nomination-eligibility**, and every identifier must say so.

*Alternative rejected:* ship `is_oz2_designated` returning `Optional[bool]`, permanently
`None`, with a docstring explaining that designations begin 2027. Rejected because this
portfolio's recurring defect is gates that misdescribe their own coverage, and a flag whose
name asserts a determination its data source cannot make is that defect in its purest form.
A name is read far more often than a docstring.

---

## 2. Q2 — Which "2020 boundaries"? (answered first: it can invalidate the restoration)

### The claim under test

S1 §3.01(3), verbatim and in full:

> **(3) Boundaries of eligible population census tracts to be designated as 2027 QOZ.**
> The 2020-2024 ACS 5-Year and 2020 DECIA data used in determining eligible population
> census tracts is collected from the geographic areas based on the population census tract
> numbers and boundaries **established for the 2020 decennial census**. Because these data
> are used to establish boundaries for eligible population census tracts that are designated
> as 2027 QOZs, such boundaries are **controlling and not subject to change** during the
> 2027 QOZ designation period.

Read as a *basis* declaration this is true and useful. Read as a statement that the
Appendix's keys will join against any other 2020-basis table, it is false — and §M1.2a of
the tract-vintage methodology is exactly why:

> Two years can share a delineation basis and still have non-comparable keys. … The
> quantity that actually governs comparability is the **GEOID scheme**: the (delineation
> basis, code assignment) pair that determines whether the same string denotes the same
> ground. **Scheme strictly dominates basis.**

§3.01(3) declares a basis. It does not declare a scheme.

### Treasury declares the scheme, and it is not the raw 2020 delineation

S4 (rural methodology), footnote 10, verbatim:

> A map of eligible tracts can be created by combining the list of eligible tracts listed in
> Revenue Procedure 2026-14, with the **2024 census tract map** found in the National
> Sub-State Geography Geodatabase, available at
> `https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.2024.html`.

and, in the body, S4 distinguishes the two explicitly:

> These imperfections are due either to technical limitations in the mapping software or
> slight shifts in census tract boundaries between the **2024 tract boundaries** and census
> tract boundaries as they appear for the **2020 Decennial Census** (and thus block
> boundaries for 2020 urban areas).

Treasury is stating that the Appendix's tract identifiers are the **2024 TIGER vintage of
the 2020 decennial delineation**, and that this vintage is not pointwise identical to the
as-published 2020 delineation. That is the answer to "which 2020 boundaries": the 2024
annual vintage, not the decennial delineation as first published.

### Verified by intersection, not by reading

Normalization is exactly this package's loader rule on **both** sides —
`str(v).strip().zfill(11)` (`nmtcmapper/data/loader.py:195`). No crosswalk, no name-based
join, no fuzzy match.

Command that produced the table (`q2_intersect.py`, reproduced in full at the end of this
section):

```
python3 q2_intersect.py
```

```
Appendix data rows            : 25332
Appendix distinct GEOIDs      : 25332
Appendix raw string lengths   : {10: 4477, 11: 20855}     # xlsx stores GEOID as int
Appendix Rural Status counts  : {'Rural': 8334, 'Non-rural': 16998}
Package universe distinct     : 85395

Appendix ∩ package            : 25016
Appendix NOT in package       :   316
```

Per state — every state and territory is 100.0% except five:

| FIPS | State (Appendix label) | Appendix | matched | missed | % |
|---|---|---|---|---|---|
| 09 | **Connecticut** | **243** | **0** | **243** | **0.0%** |
| 60 | American Samoa | 16 | 0 | 16 | 0.0% |
| 66 | Guam | 20 | 0 | 20 | 0.0% |
| 69 | Northern Mariana Islands | 19 | 0 | 19 | 0.0% |
| 78 | U.S. Virgin Islands | 18 | 0 | 18 | 0.0% |
| 72 | Puerto Rico | 712 | 712 | 0 | 100.0% |
| — | all 45 remaining states + DC | 24,304 | 24,304 | 0 | 100.0% |

### Connecticut, named

```
CONNECTICUT
  Appendix rows labeled state='Connecticut' : 243
  county-FIPS prefixes present in Appendix  : 09110(72) 09120(41) 09130(5) 09140(25)
                                              09150(4)  09160(7)  09170(40) 09180(17)
                                              09190(32)
  Package tracts with state FIPS 09         : 883
  county-FIPS prefixes present in package   : 09001(227) 09003(235) 09005(52) 09007(41)
                                              09009(199) 09011(67)  09013(32) 09015(30)
  CT Appendix ∩ package                     : 0
```

Run against the **full** Treasury universe (S5, 85,529 rows) rather than the eligible
subset, so the result is not an artifact of eligibility filtering:

```
CT in Treasury file : 884 tracts, prefixes 09110…09190
CT in package       : 883 tracts, prefixes 09001…09015
full-GEOID overlap  : 0
6-digit tract-code overlap : 881 of 881 / 881   (B-only codes: []  P-only codes: [])
```

The six-digit tract codes are **identical sets**. Only the five-digit county prefix differs.
This is a pure relabeling — the Connecticut county-equivalent renumbering (87 FR 34235),
which replaced CT's eight legacy counties with nine COG/planning regions. The Appendix
carries the **new** COG codes; the CDFI Fund table this package is built on carries the
**legacy** county codes, as `nmtcmapper/data/schema.py` already documents at lines 8–24.

**The brief's guess was backwards** — it proposed "Appendix 09001–09015 / package
09110–09190 (or the reverse)". It is the reverse.

### Decision

**A direct key join between the OZ 2.0 Appendix and this package's tract table is
invalid, and must not be performed.** It silently drops Connecticut entirely (243 of 243
eligible tracts) and all four DECIA territories (73 tracts) — 316 tracts, 1.2% of the
eligible universe, concentrated so that two whole jurisdictions read as "no eligible
tracts." That is the 0.4.1 Connecticut defect reproduced in a new place, and it is
*worse* here than in 0.4.1, because in 0.4.1 the failure surfaced as `not found`; a naive
OZ 2.0 join would surface it as a confident negative.

**Two schemes, therefore two bindings.** Any OZ 2.0 table must carry its own
`TractVintage`-shaped binding, constructed and validated separately from `TRACT_VINTAGE`,
and the two must never be assumed interchangeable. The existing frozen dataclass in
`nmtcmapper/data/schema.py` is the correct pattern and should be followed — but note that
its `__post_init__` checks `basis_year` against `geocoder_vintage` and
`table_geoid_header`, all three of which would read "2020" for **both** schemes. **The
existing guard cannot distinguish these two tables.** A scheme discriminator — not a
basis year — is what a new binding needs. This is §M1.2a's finding arriving as a concrete
design constraint on this package: *scheme strictly dominates basis*, and the 0.4.1 guard
encodes basis.

*Alternative rejected:* crosswalk CT's 09110–09190 back onto 09001–09015. The mapping is
mechanically available and, unlike the 2010↔2020 case, is even bijective at the tract-code
level (881↔881). It is still refused, for §M5's reason: the package would be silently
converting a *published federal determination keyed to one geography* into an *inferred
determination on another*, changing nothing about the column name, the dtype, or the row
count. §M5's rule — "a library that ships a screening tool should not silently model" —
applies unchanged, and this is an eligibility determination for a federal tax credit.
The refusal is stated to the user, not hidden.

*Alternative rejected:* re-key the package's NMTC table onto the COG scheme so both tables
join. That would make this package's NMTC answers disagree with the CDFI Fund's own
published table, which is the authority for NMTC. The CDFI Fund keeps legacy CT county
data by decision (NMTC LIC ACS FAQ, Feb 1 2024, General Q4, as recorded at
`schema.py:16-17`). NMTC follows the CDFI Fund; OZ 2.0 follows Treasury/IRS. They differ,
and the honest representation of that is two tables, not one reconciled one.

---

## 3. Q1 — Is absence from the Appendix a returnable `False`?

Recast, since §1 removed the designation framing: *is absence from the Appendix a returnable
`False` for **nomination-eligibility**?*

### Primary text

S1 §5.04, verbatim and in full:

> **.04 Data set limitations.** While the Appendix to this revenue procedure and the
> Information Resource provide a list of population census tracts that are eligible for
> nomination as a QOZ, **there may be population census tracts that could be eligible for
> nomination as a QOZ that do not appear on this list.** The Secretary will consider a
> State CEO's nomination of a population census tract **not listed in the Appendix** or
> Information Resource to the extent that the nomination is accompanied by a detailed
> analysis, including current data collected at the census tract level, demonstrating the
> nominated population census tract satisfies the requirements under § 1400Z-1(c)(1).

This is dispositive and requires no inference. The Revenue Procedure states in its own
words that the Appendix is **not exhaustive**, and reserves a live mechanism by which an
unlisted tract can be nominated and designated. Absence from the Appendix is therefore
"not on Treasury's list," which is strictly weaker than "not eligible."

### Decision — and it is split, because there are two sources

**From the Appendix (S2): absence is `None`, not `False`.** §5.04 forecloses the
exhaustiveness reading directly.

**From the Treasury data-transparency file (S5): a real `False` is available, and should
be used.** S5 is not a list of the eligible; it is the **full tract universe with an
explicit flag**:

```
B rows                : 85529
B eligible_lic values : {0: 60197, 1: 25332}
B rural_status values : {1: 28711, 0: 56818}
```

Its `Notes` sheet defines the field in the file's own words:

> **eligible_lic** — If either poverty_rate of the tract is at least 20 percent and
> mfi_ratio does not exceed 125 percent or if mfi_ratio does not exceed 70 percent, then
> the tract is an eligible low-income community (LIC). eligible_lic equals 1 if the tract
> is an eligible LIC and **0 otherwise**.

This is the same structural argument the package already makes for NMTC at
`nmtcmapper/data/loader.py:1-6` — a full universe carrying an explicit YES/NO makes a `NO`
a fact, and reserves `None` for genuine absence from the universe. It reproduces here.

The two sources agree perfectly, which is worth stating because it is the evidence that S5
is the same determination and not a near-miss:

```
A ∩ B_eligible          : 25332
in A, NOT eligible in B : 0
eligible in B, NOT in A : 0
rural-flag disagreements on shared set: 0
```

**So: `False` is returnable — but only for tracts present in S5, and only sourced from
S5's `eligible_lic == 0`.** A tract absent from S5's 85,529-row universe is `None`. A
tract present in S5 with `eligible_lic == 0` is `False`, and the reason it is safe is
§5.04 itself: §5.04's escape hatch is about tracts missing from *the list of the eligible*,
and requires the nominating State to supply "current data collected at the census tract
level" — i.e. data other than the 2020-2024 ACS. It does not assert that S5's arithmetic
on the stated inputs is wrong for a tract S5 scored. `False` therefore means *"not an
eligible LIC on the 2020-2024 ACS / 2020 DECIA inputs Treasury used"* — which is a fact
about a published determination, and the docstring must say exactly that rather than
"not eligible."

The brief is right that over-refusal is its own failure mode and that this portfolio has
shipped one. The correct response is not to loosen the Appendix's contract; it is to load
the source that actually carries negatives.

*Alternative rejected:* return `False` for absence from the Appendix. Rejected on §5.04's
plain text. This would also have made the Q2 result catastrophic rather than merely wrong:
243 Connecticut tracts would have returned a confident `False`.

*Alternative rejected:* use only the Appendix (S2), tri-state, `True`-only, matching
`oz-tracker` 0.2.0. Rejected because S5 is live, is Treasury's own publication, is named
as authoritative by the Appendix's companion methodology, and agrees with S2 on all 25,332
rows. Refusing to return a negative that a full-universe federal file explicitly publishes
is the over-refusal failure mode.

### One caution on S5's stability

The Appendix's only sheet is named **`Appendix for Designation RP_cor`** — the `_cor`
suffix reads as *corrected*. S5's file is *named* `…03232026` but its OOXML
`dcterms:created` is **2026-04-06T14:21:34Z**, the Rev. Proc.'s effective date, two weeks
after the date in its own filename. Neither fact proves a prior version's contents differed;
together they are enough that the loader must **not** treat either file as immutable. Pin
by digest, re-verify on load, and fail loud on a row-count or column-name change — the
guard this package already has for the NMTC table (`_validate_xlsb_header`), which is
earning its keep today (see §6).

---

## 4. Q3 — What does `is_rural` mean here, and is it a separate fact?

### It is a statutory classification, not a property of the tract

S1 §2.01(4)(a)(iii), verbatim:

> **(iii) Rural area.** Section 1400Z-2(b)(2)(C)(ii) defines the term "rural area" as any
> area other than (1) a city or town that has a population of greater than 50,000
> inhabitants and (2) any urbanized area contiguous and adjacent to a city or town that has
> a population of greater than 50,000 inhabitants.

The definition sits in **§ 1400Z-2**, the *investment/benefit* section, not § 1400Z-1, the
*designation* section — and it exists to define a fund. S1 §2.01(4)(a)(ii):

> **(ii) Qualified rural opportunity fund.** Section 1400Z-2(b)(2)(C)(i) defines the term
> "qualified rural opportunity fund" (QROF) as a QOF that holds at least 90 percent of its
> assets in QOZP that is— (A) QOZBP substantially all of the use of which … was in a QOZ
> **comprised entirely of a rural area** …

and it has an effective date of its own — S1 footnote 2:

> Section 70421(c)(2) of the OBBBA added § 1400Z-2(b)(2)(C)(i) to the Code, **effective for
> amounts invested in QOFs after December 31, 2026.**

So the flag's referent is not "this tract is rural." It is: *"this tract, **if** nominated
and **if** designated, would be a QOZ comprised entirely of a rural area, and therefore
QOZBP there could support QROF qualification for amounts invested after 2026-12-31."*
Three conditionals, none of which the package can evaluate.

The statutory phrase is **"comprised entirely of a rural area"** — a predicate over the
tract's whole area — and S4 confirms the derivation is areal and multi-step, not a
tract attribute lookup:

> Those eligible tracts with no area overlapping the identified cities, towns, or urban
> areas are deemed to be comprised entirely of a rural area; accordingly, Treasury
> determines these to be rural eligible tracts.

S4 also documents a **de minimis rule** that admits tracts which *do* overlap an urban
area, provided the overlap "does not completely contain at least one census block" that is
urban or inside a >50,000 city. A user reading `is_rural=True` as "no urban land in this
tract" would be wrong on those tracts, by Treasury's design.

And S4's inputs carry their own geographies: 2020 Decennial city/town populations, 2020
Decennial urban areas at block level, CDPs substituting for cities in Hawaii and Puerto
Rico — with the tract polygons themselves on the 2024 TIGER vintage (footnote 10, §2 above).

### Decision

**Ship it, renamed, with the statutory context in the docstring — or do not ship it.**

- The name `is_rural` is rejected: on an eligibility result it asserts a property of the
  tract. The proposed name is **`is_rural_area_qoz_eligible`** (or any name that carries
  both "rural area" as the statutory term and the eligibility qualifier). The exact
  identifier is an API decision and out of scope here; the *requirement* is that the name
  not assert tract ruralness.
- The docstring must carry, at minimum: (a) the § 1400Z-2(b)(2)(C)(ii) definition; (b) that
  the consequence is QROF qualification for amounts invested after 2026-12-31, conditional
  on the tract actually being nominated and designated; (c) that "comprised entirely of a
  rural area" is subject to Treasury's de minimis overlap rule and is therefore not
  "contains no urban land."
- Without (a)–(c) the flag does not ship. This is the brief's own test and it is the
  right one.

### Two facts, and only one is safe to expose

S5 carries `rural_status` for the **entire** 85,529-row universe: 28,711 tracts are
`rural_status == 1`, of which only 8,334 are also `eligible_lic == 1`. S4, however,
describes the determination as applied to *eligible* tracts:

> This document describes the methodology that the Department of the Treasury (Treasury)
> used to identify which census tracts eligible to be nominated as 2027 QOZs in Revenue
> Procedure 2026-14 (eligible tracts), are comprised entirely of a rural area (rural
> eligible tracts).

**Decision: expose `rural_status` only where `eligible_lic == 1`** — 8,334 tracts. For the
20,377 tracts flagged rural but not eligible, return `None`. The published,
methodology-backed determination is over rural *eligible* tracts; the ineligible rows'
flag is present in the file but outside what S4 documents, and nothing turns on it (a
non-eligible tract cannot become a QOZ, so QROF qualification cannot arise).

*Alternative rejected:* expose `rural_status` across the full universe because the column
is populated. Rejected — the column being populated is not the same as the determination
being published. That inference ("it has a lot of rows, therefore it is authoritative") is
the exact move the brief forbids for the Appendix, and it is no better here.

### Disagreement with `oz-tracker` — noted, nothing changed

`oz-tracker` 0.2.0 exposes `OZ2Checker.is_rural(tract_id) -> Optional[bool]`, `True`-only,
docstring: *"A True is a fact; the absence of True is 'not confirmed', not 'not rural'."*
Three differences will exist, and all three are this package being more conservative or
more correct — none is a reason to change `oz-tracker`, which is out of scope:

1. **Name.** `oz-tracker` calls it `is_rural`; this package will not.
2. **Answer space.** `oz-tracker` cannot return `False`; this package will, from S5, on the
   eligible subset.
3. **Derivation.** `oz-tracker` does not read the published list at all. Its
   `OZ2Checker._process` re-derives eligibility from thresholds via
   `check_oz2_eligibility(poverty_rate, ami_ratio)` against `OZ2_MFI_THRESHOLD = 0.70` /
   `OZ2_POVERTY_THRESHOLD = 0.20`. It also carries a documented column-case defect and a
   dead URL, both acknowledged in its own docstrings, so in 0.2.0 it returns `None`
   universally in practice.

**The disagreement is currently latent, not live** — `oz-tracker` 0.2.0 answers `None` for
every tract. It becomes live the moment `oz-tracker`'s URL and column-case defects are
fixed. The portfolio-level resolution (one package defers to the other, or both are
re-pointed at S5) is a decision for whoever fixes `oz-tracker`; this note only records that
the collision is scheduled.

For the record, `oz-tracker`'s dead URL is
`https://home.treasury.gov/system/files/136/Eligible-LICs-for-Nomination-as-2027-QOZs.xlsx`
→ **HTTP 404**. The live file is at
`https://home.treasury.gov/system/files/131/OZ2-Eligible-LIC-Tracts-Data-Transparency-03232026.xlsx`.
Both the directory *and* the filename changed; `/system/files/131/Eligible-LICs-for-Nomination-as-2027-QOZs.xlsx`
also returns **HTTP 404**.

---

## 5. Proposed flags and their answer spaces

Names are indicative; the binding commitment is the answer space and the source.

| Flag | Source | `True` | `False` | `None` |
|---|---|---|---|---|
| `is_oz2_nomination_eligible` | S5 `eligible_lic` | tract in S5 and `eligible_lic == 1` (25,332) | tract in S5 and `eligible_lic == 0` (60,197) — *"not an eligible LIC on the 2020-2024 ACS / 2020 DECIA inputs Treasury used"* | tract not in S5's 85,529-row universe, **or** tract key is on a scheme other than S5's (see Q2) |
| `is_rural_area_qoz_eligible` | S5 `rural_status`, restricted to `eligible_lic == 1` | `eligible_lic == 1` and `rural_status == 1` (8,334) | `eligible_lic == 1` and `rural_status == 0` (16,998) | everything else — including all 60,197 ineligible tracts, whatever their `rural_status` |
| `is_oz2_designated` | — | **not proposed.** No designation exists before late 2026 (§1). | | |

Both flags are `Optional[bool]`. `True` and `False` are facts about a published federal
determination; `None` is "not determined," never "no."

The tri-state contract from `oz-tracker` 0.2.0 remains the default answer space. This note
establishes that one source — and only S5 — clears the bar to return `False`, and does so
on §5.04's own text plus the file's own `Notes` definition, not on an inference from row
count.

---

## 6. What this does not establish

Written plainly, because gates in this portfolio that misdescribed their own coverage
became defects later.

1. **No designation is established, and none can be.** Every flag above concerns
   *eligibility for nomination*. A tract that is `True` may never be nominated, and a
   nominated tract may not be certified. §5.04 also permits designation of a tract that is
   `False` here. There is no OZ 2.0 designation determination in this package, in
   `oz-tracker`, or in any federal publication as of 2026-08-05.

2. **The 25% per-State cap is not modeled.** S1 §3.01(1) states the 25-percent limitation
   is determined on the same data sets. No flag here reflects it. A State's eligible tracts
   materially exceed what it may nominate, so `True` is not "will be an OZ."

3. **The Connecticut tracts are not resolved — they are refused.** For any CT tract keyed
   on the CDFI Fund's legacy 09001–09015 scheme, every OZ 2.0 flag is `None`. This is a
   correct `None` and a real coverage gap: 243 eligible CT tracts, and 884 CT tracts
   overall, are unanswerable through the package's existing NMTC key. A user who wants a CT
   answer must supply a 09110–09190 key. **The package must say this out loud** — a silent
   `None` for an entire state is the misdescription failure mode.

4. **The four DECIA territories are outside the package's tract universe entirely.**
   American Samoa (60), Guam (66), CNMI (69) and USVI (78) — 133 tracts in S5, 73 of them
   eligible — have no row in the CDFI Fund NMTC table at all. Puerto Rico (72) does and
   matches 712/712.

5. **This note does not verify Treasury's arithmetic.** S3's criteria were read; the
   ACS/DECIA extractions behind `eligible_lic` were not recomputed. `False` means "Treasury
   published 0," not "0 is correct."

6. **The rural determination's spatial work is not verified.** S4's block-level overlap,
   contiguity, island exclusions, and de minimis rule were read, not reproduced. No
   geospatial check was performed.

7. **Source stability is not established.** Both files are pinned by digest as of
   2026-08-05. The `_cor` sheet name and S5's created-date/filename mismatch (§3) are
   reasons to expect revision, not evidence of a specific past revision. No prior version
   of either file was obtained.

8. **The GEOID-scheme finding is empirical for the tables actually compared.** It shows the
   two schemes are disjoint in CT and identical in the other 49 states + DC + PR *for these
   two files on this date*. It does not license a general rule about future CDFI Fund or
   Treasury releases, and it is not a crosswalk (§M5).

9. **The 2024-TIGER binding rests on S4 footnote 10 plus the CT intersection.** Treasury
   nowhere labels the Appendix "2024 vintage" in a single normative sentence; S1 §3.01(3)
   says "2020 decennial census." The reading here — basis 2020 decennial, scheme 2024
   annual vintage — reconciles the two and is confirmed by the CT keys. It is a reading,
   and it is the load-bearing inference in this document.

10. **A blocking defect was found in the package's existing NMTC path and is not fixed
    here.** It is reported below because 0.5.0 would otherwise ship on top of it.

---

## 7. Blocking defect found in passing — nmtc-mapper 0.4.1 cannot load live data today

Out of this note's scope, not fixed on this branch, reported because it gates 0.5.0.

The CDFI Fund has re-published the `.xlsb` at the **same URL** (`CDFI_FUND_LIC_URL_2020`)
with two renamed headers. `_validate_xlsb_header` compares them and raises:

```
col count 16 expected 16
  FAIL  2
      expected: Does Census Tract Qualify For NMTC Low-Income Community (LIC) on Poverty or Income Criteria?
      live    : Does Census Tract Qualify For NMTC Low-Income Community (LIC) on Poverty or Income Criteria or High Migration Rural Census Tract?
  FAIL  13
      expected: High Migration County Low-Income Community Census Tract
      live    : High Migration Rural County Low-Income Community Census Tract

MISMATCHES: 2 -> loader RAISES EligibilitySchemaError
```

Every non-sample construction of `NMTCMapper` therefore fails today. The guard behaved
exactly as designed — it caught a real upstream change rather than mis-binding columns —
but the column-2 rename is **semantic**, not cosmetic: the LIC flag now also covers
high-migration-rural qualification. Updating the two constants without re-verifying what
column 2 now means would be the wrong fix.

Separately, and pre-existing: `DEEP_AMI_THRESHOLD = 0.50` and
`DEEP_UNEMPLOYMENT_MULTIPLIER = 2.0` in `schema.py` do not match the live file's own
column-15 header, `Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)`. These
constants are used only by `_compute_eligibility`, not by the live `.xlsb` path (which
reads the precomputed columns 14/15), so no live verdict is currently wrong — but the two
definitions of "deep distress" in one package disagree.

Also stale: `schema.py:105-106` states "OZ 2.0 designations expected 2027," which is
correct, and "Made permanent by One Big Beautiful Bill Act (2025)," which is correct — but
the comment predates Rev. Proc. 2026-14 and does not record that the eligibility list now
exists.

---

## Appendix — the command that produced the Q2 result

```python
# q2_intersect.py — normalization on BOTH sides is exactly the loader's rule:
#   str(v).strip().zfill(11)      (nmtcmapper/data/loader.py:195)
# No crosswalk, no fuzzy match. Intersection only.
import collections, openpyxl
from pyxlsb import open_workbook

wb = openpyxl.load_workbook("rp-26-14-appendix.xlsx", read_only=True)
rows = wb.worksheets[0].iter_rows(values_only=True); next(rows)
appx = {str(r[2]).strip().zfill(11): (r[0], r[3]) for r in rows if r[2] is not None}

pkg = set()
with open_workbook("nmtc.xlsb") as b, b.get_sheet("2016-2020") as sh:
    for i, row in enumerate(sh.rows()):
        if i == 0 or row[0].v is None: continue
        s = str(row[0].v).strip()
        pkg.add((s[:-2] if s.endswith(".0") else s).zfill(11))

print(len(appx), len(pkg), len(set(appx) & pkg), len(set(appx) - pkg))
by_state = collections.defaultdict(lambda: [0, 0])
for g in appx:
    by_state[g[:2]][0] += 1
    by_state[g[:2]][1] += g in pkg
for f in sorted(by_state): print(f, by_state[f])
```

Inputs, by digest:

- `rp-26-14-appendix.xlsx` — `5e21ee2f88edfe871f75b5c5a0b5a6c8cc20d9ac74fffe3c4cc11f4c39c46969`
- `nmtc.xlsb` — `3a6f5851b836ba4b8c31aac48b7ededd761dd002a8831ebebb4d69a428772d49`
- `treas_oz2.xlsx` (S5) — `9d41e6581475ff23f0db2b889d01284de4f996d08e71ca72a6a4031d57e37dc0`
- `rp-26-14.pdf` (S1) — `bf8538c79170c8129890f6650561d72f1cd83150d9ab1de40bb43bcbdd191032`
- `OZ2-Eligibility-Criteria-Data-Transparency-03232026.pdf` (S3) — `2c9a1a7fc4cbff17bcb2c48dbac4d6dbbca5ec6edef0e7a169111474da2c6e30`
- `OZ2-Rural-Area-Notice-Methodology-Data-Transparency-03232026.pdf` (S4) — `f42c01c1e1dca8d174ce7f5c8951b9a1a6be2c5fe668e8a2a8c88cdea5d85ce8`

All fetched 2026-08-05.
