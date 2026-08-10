# Changelog

All notable changes to nmtc-mapper are documented here.

## [0.4.3] — 2026-08-09

Documentation accuracy. **No logic changes — prose, comments and this file
only.** Every `.py` file in the 0.4.3 wheel is byte-identical to its 0.4.2
counterpart except for comment lines in `nmtcmapper/data/schema.py`; no shipped
verdict, count or threshold moves.

0.4.2 corrected three distress constants in `schema.py` and this CHANGELOG, and
left the README asserting the superseded numbers — because the README correction
was scheduled to a later release. The README is the long description, so those
numbers rendered on the PyPI project page: the package's front door. This release
removes that coupling.

### Fixed
- **The README stated four wrong values in the CDFI Fund's distress criteria,
  not two.** The scoping everyone repeated was "MFI 50→40 and 2×→2.5×". The same
  sentence also stated both poverty prongs with the wrong comparison.

  | | README said | Now says |
  |---|---|---|
  | severe poverty | `>= 30%` | `> 30%` |
  | deep poverty | `>= 40%` | `> 40%` |
  | deep MFI | `<= 50%` AMI | `<= 40%` AMI |
  | deep unemployment | `>= 2x` national | `>= 2.5x` national |

  Authority, re-derived this release against the live workbook
  (`3a6f5851…428772d49`, 85,395 rows) rather than relayed:
  1. The workbook's own data-sheet headers — column 14
     `Severe distress=LIC AND (Poverty>30%; MFI<=60%;Unemployment>=1.5)`,
     column 15 `Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)`
     — identical to the NOTES sheet's *Column O* / *Column P* rows.
  2. The CDFI Fund's *NMTC Compliance Monitoring and Evaluation FAQs*
     (cover: **UPDATED APRIL 2025**; 64 pages; SHA-256 `8d75e98a…7a0b806a`),
     **Q32**: poverty rates *"greater than 40%"*, MFI that *"does not exceed
     40%"*, *"unemployment rates at least 2.5 times the national average"*.
  3. Fit against the published flags: `> 40% OR MFI <= 40% OR ratio >= 2.5`
     mismatches on **3** of 85,395 rows; the superseded `MFI <= 50% / >= 2.0`
     pair mismatches on **5,025**. On poverty, `>` mismatches on 20 severe /
     3 deep and `>=` on 41 / 16.

  **The three values not changed are confirmed right:** severe MFI `<= 60%`
  (20 mismatches; the nearest alternatives 0.55 and 0.65 give 1,745 and 2,287)
  and severe unemployment `>= 1.5x` (20; 1.25× and 1.75× give 2,083 and 1,622).

- **The README now says why LIC uses *at least* and distress uses *strictly
  greater*.** Two comparisons in one document is the kind of thing a later
  reader "fixes" into consistency, so the reason is stated at the point of use.
  LIC poverty stays `>= 20%` — §45D(e)(1)(A) says a poverty rate "of at least 20
  percent", and the Fund's own column-4 header reads *"Does Census Tract Qualify
  on Poverty Criteria>=20%?"* and flags YES on all 163 tracts at exactly 20.0%.
  The distress prongs are strict. The boundary population is not hypothetical:
  83 LIC tracts sit at exactly 30.0% poverty and 29 at exactly 40.0%; of those
  qualifying on poverty alone, the Fund published `severe = NO` for **all 21**
  and `deep = NO` for **all 13**.

- **`schema.py`'s two distress comments no longer contradict each other.**
  Line 72 read `# >= 30% poverty rate` while line 108 read `# > 40%`. Both now
  read `# Fund criterion: > N% poverty rate`, with a block comment recording the
  authority, the deliberate `>=` on the LIC prong above them, and the
  `_compute_eligibility` caveat below. **No constant changed.**

- **Native Areas were categorised as *Areas of Higher Distress*. They are
  *Areas of Deep Distress*.** FAQ Q32 enumerates them as item 2 — *"NMTC Native
  Areas: Federal Indian Reservations, Off-Reservation Trust Lands, Hawaiian Home
  Lands, and Alaska Native Village Statistical Areas."* Q31's eleven Areas of
  Higher Distress resources (Brownfields, HUB Zones, MUA/HPSA, ARC, DRA,
  low-access tracts, Promise Zone, FEMA, Impacted Coal Counties, BRAC, QOZ) do
  not include them; "Native" appears nowhere else in the FAQ's body.

  **The 0.4.1 entry below is wrong in the same way and is corrected here, going
  forward, not in place.** `CHANGELOG.md` ships inside the published 0.4.1 and
  0.4.2 sdists, which are immutable. Editing a historical entry would silently
  diverge this repo from artifacts PyPI is still serving. This portfolio made
  that mistake once and reverted it.

  The README also now states plainly, where it names the field, that
  `is_nmtc_native_area` carries no information: a `False` never means "checked
  and not a native area." Removing the field remains 0.5.0's; this release only
  stops mis-describing it.

- **US Island Areas: a gap in a named federal criterion, now disclosed.** FAQ
  Q32 item 4 names *"US Island Areas … including Puerto Rico, U.S. Virgin
  Islands, Guam, the Commonwealth of the Northern Mariana Islands, and American
  Samoa"* as a Deep Distress criterion. The eligibility file covers the 50
  states, DC and **Puerto Rico (981 tracts — named in the criterion and present
  in the file)**, and contains **zero rows for FIPS 60 / 66 / 69 / 78** —
  American Samoa, Guam, the Northern Marianas, the US Virgin Islands. That is
  **133 census tracts** on 2020 geography (18 / 57 / 26 / 32, per the Census
  2020 TIGERweb tract layer and the TIGER/Line 2020 tract files, which agree).
  Neither the README nor this CHANGELOG had mentioned Island Areas at all; the
  README's Data Sources section now describes the universe and this boundary.
  Such a tract is reported `nmtc_eligible = None` / `distress_level = "unknown"`
  — absent from the universe, not ineligible.

- **`docs/eligibility.md` carried the identical wrong distress table** (`Deep |
  >= 40% | <= 50% | >= 2x national`) and is corrected the same way. It is not
  shipped in the sdist, but it is published to the documentation site, so fixing
  only the README would have repeated 0.4.2's error of correcting one surface
  and leaving another.

### Recorded, not fixed
- **`docs-check.toml:60-65` deliberately excludes prose claims**, naming "the
  eligibility thresholds in the distress table" as unguarded. The repo knew this
  claim was machine-unverifiable and shipped it wrong anyway. A prose-claim
  assertion is the durable fix; it needs design and belongs to **0.5.0 or
  later**. No gate logic is added here — new gate logic in a doc patch is scope
  creep.
- **Two stale "114 tests" references in `docs-check.toml`** — line 33 (a pattern
  example) and line 120 (the claim that assertion 3 passes). The suite is
  **140**. Comments only; the gate reads neither number.
- **`_compute_eligibility` (`loader.py:463`, `:468`) compares poverty with `>=`
  against both distress constants**, so the fallback is over-inclusive at
  exactly 30.0% / 40.0% relative to the Fund's `>`. It is reachable only from
  the synthetic sample — the official `.xlsb` path reads the published columns
  14/15 — so no shipped verdict is affected. Correcting it is a **logic change**
  and belongs to 0.5.0.
- **The `cdfi-superpowers` `nmtc-eligibility` skill was checked and does *not*
  carry the Higher/Deep mis-categorisation.** The string "Areas of Higher
  Distress" appears nowhere in that repository, and the skill quotes no distress
  thresholds. Recorded so the check is not repeated. Its `is_nmtc_native_area`
  note is accurate as written.

## [0.4.2] — 2026-08-05

Hotfix. The CDFI Fund re-published the eligibility file in place; every live
load had been failing. Corrects a shipped false negative on 168 census tracts,
and three distress thresholds that disagreed with the CDFI Fund's own
definitions.

### Fixed
- **168 census tracts were reported as not NMTC-eligible when they were
  eligible, in every release from v0.3.1 to v0.4.1.** This is the substantive
  content of the release: a false negative in an eligibility tool.

  A Low-Income Community is defined at 26 U.S.C. §45D(e). There are three routes
  in: a poverty rate of 20% or more, a median family income at or below 80% of
  the applicable area MFI, and — added by section 223 of the American Jobs
  Creation Act of 2004 (P.L. 108-357), now **§45D(e)(5)** — a tract in a *high
  migration rural county* with MFI at or below **85%** of the applicable area
  MFI. A high migration rural county is one with net out-migration of at least
  10% of its population over the 20 years ending with the most recent census.

  The CDFI Fund's workbook published the first two routes in column C and the
  third in column N. nmtc-mapper read **column C as the entire verdict** from
  ccaab24 (v0.3.1, 2026-05-14 — the commit that added the `.xlsb` path) onward,
  so the 168 tracts whose only route in is §45D(e)(5) came back
  `nmtc_eligible=False`, `distress_level="ineligible"`, while the very same row
  reported `is_high_migration_rural=True`. Six tagged releases carried it —
  v0.3.1, v0.3.2, v0.3.3, v0.3.4, v0.4.0, v0.4.1 — from 2026-05-14 until this
  release, 83 days.

  **The verdict is now column C `OR` column N.** That is the Fund's own rule:
  across all 85,395 rows of the live file, published column C is exactly
  `column D OR column G OR column N` (the ≥20% poverty flag, the ≤80% MFI flag,
  and the high-migration-rural LIC flag) with **zero mismatches**. Column N is an
  LIC *determination*, not bare county membership — its 1,422 `YES` tracts sit in
  437 counties holding 1,883 tracts between them, and every one of the 1,422
  satisfies a statutory prong (757 on poverty, 1,084 on MFI ≤80%, and the
  remaining 168 in the 80–85% band). If it had meant "sits in a high migration
  rural county", OR-ing it would have granted LIC status to tracts above 85% MFI
  — the mirror of the defect being fixed.

  **On the file as published today this change moves nothing.** The July-2026
  re-publish widened column C to absorb column N, so all 1,422 column-N `YES`
  rows are already column-C `YES`: the eligible count is 35,335 with the OR and
  35,335 without it, and the distress split is identical
  (`ineligible` 50,060 / `lic` 14,153 / `severe` 13,121 / `deep` 8,061).
  What changes is *why* it is right. Reading column C alone is correct only for
  as long as the Fund keeps the columns merged, and nothing in the loader would
  notice if they separated again: fed a file with the July-2026 headers and a
  column C reverted to poverty/income only, the header pins match, the row-count
  floor and value bounds pass, and the eligible count silently drops back to
  35,167. `tests/test_schema_validation.py` now reproduces exactly that file
  offline, so the gate runs in CI rather than only under `-m live`.

- **Live data loads again.** On 2026-07-22 (per the URL's `last-modified`
  header; the file's NOTES sheet says "July 2026") the CDFI Fund re-published the
  eligibility workbook at the **same URL, under the same filename**
  (`NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb`) with two renamed
  column headers. The loader binds columns positionally and pins the exact
  header strings, so `_validate_xlsb_header` raised `EligibilitySchemaError` and
  **every non-sample `NMTCMapper()` failed**. The guard behaved correctly — it
  refused to read a changed file against stale positions. The pins have been
  updated to the new strings:

  | Index | Was (Aug-2025b) | Now (July 2026) |
  |---|---|---|
  | 2 | …on Poverty or Income Criteria? | …on Poverty or Income Criteria **or High Migration Rural Census Tract**? |
  | 13 | High Migration County Low-Income Community Census Tract | High Migration **Rural** County Low-Income Community Census Tract |

  Index 13 is cosmetic: its 1,422 `YES` values are byte-identical to the prior
  release. Index 2 is not — see below.

- **A stale cache no longer defeats the upgrade.** `download_eligibility_file()`
  returns the cached copy whenever one exists, and the Fund re-publishes under
  an unchanged filename — so upgrading alone would still have failed for anyone
  who had run 0.4.1, because the new pins would be validated against the old
  cached bytes, and the error would have told them to upgrade. A schema mismatch
  on a **cached** file now re-downloads once and re-validates. The guard is not
  weakened: the fresh file is checked just as strictly, a genuine divergence
  still raises, the retry happens at most once, and `force=True` never retries.

- **A bad download can no longer destroy the cache.** `raise_for_status()` passes
  on an HTTP 200, so an HTML maintenance page — the shape a CDN/origin stack in
  front of this URL serves during an outage — used to stream cleanly to the
  `.part` temp and then `tmp.replace()` straight over a good 4.8 MB workbook.
  Worse, the resulting failure was an `EligibilityParseError`, which is a
  *sibling* of `EligibilitySchemaError` rather than a subclass, so the stale-cache
  self-heal above never caught it and never re-downloaded. Every subsequent run
  read the 133 bytes of HTML from cache, failed, and attempted no download — with
  a perfectly healthy network. The package stayed broken until the user found and
  deleted `~/.nmtcmapper/cache` themselves, and the error message named the path
  but offered no remedy.

  Two changes. The download now proves the body is an OOXML/ZIP container
  (`PK\x03\x04`, plus a minimum size) **before** `tmp.replace()`, so a wrong body
  never reaches the cache path at all — on a cold cache nothing is installed, and
  on a warm one the existing file survives byte-for-byte. And the self-heal now
  covers `EligibilityParseError` as well as `EligibilitySchemaError`, so a cache
  already poisoned by an earlier release repairs itself on the next run. The
  at-most-once cap is unchanged and remains structural: the handler calls the
  private `_load_eligibility_table(force=True)`, not the public wrapper, so the
  retry cannot re-enter the heal. A heal attempt that fails at the network layer
  leaves the cached bytes exactly as it found them. The Opportunity Zone download
  had the same `tmp.replace()` shape and now carries the same pre-replace guard.

### Changed — user-visible eligibility
- **Upstream widened column C, which is why 0.4.2 reads the 168 correctly even
  before the fix above.** As of the July-2026 re-publish, column C also carries
  High Migration Rural tracts. The file's own NOTES sheet states: *"In July 2026,
  the dataset was reformatted to include High-Migration Rural Census Tracts under
  COLUMN C. Only formatting changes were made. No eligibility changes were
  made."*

  That last sentence is true of the **statute** and false of the **column**. A
  row-level diff of the two published files (all 85,395 tracts, every cell)
  shows exactly one column changed: **column C, 168 tracts, all `NO` → `YES`**.
  Columns A, B, D–P are byte-identical, including the severe and deep distress
  flags. All 168 are High Migration Rural, all are non-metro, none qualifies on
  poverty (≥20%) or on MFI ≤80%, and every one has a benchmarked MFI ratio in the
  80–85% band — measured across the 168, from 0.800154 to 0.849885 — i.e. they
  qualify solely under the ≤85% MFI provision at 26 USC §45D(e)(5).

  Those tracts were **always** NMTC-eligible; the prior file simply expressed it
  in column N. The Aug-2025b workbook said so outright, in a
  `High migration tracts` sheet the re-publish dropped: it listed exactly these
  168 tracts as "census tracts that have become eligible for NMTC investments
  pursuant to the American Jobs Creation Act", above a 520-county table headed
  *"High Migration Counties (only Low-Income Community census tracts within
  counties are eligible)"*.

  Effect on the table: eligible tracts go 35,167 → **35,335**; ineligible
  50,228 → **50,060**. All 168 move `ineligible` → `lic`. No tract changes in
  the other direction, and no tract changes severe/deep status.

  **Releases before v0.3.1 were not affected**, by accident rather than by
  design. The retired `.xlsx` path ran `_compute_eligibility()`, whose `ami_lic`
  term grants the ≤85% band to *every* non-metro tract rather than only to those
  in high migration rural counties — so it returned eligible for all 168, and for
  932 tracts in total that the Fund publishes as ineligible. A right answer from
  an over-inclusive rule. **This is established at the code level and could not
  be executed end-to-end:** the pre-v0.3.1 source URL now redirects to a 404
  (verified), and no archived copy could be retrieved, so the `.xlsx` itself is
  unavailable. Executing the
  v0.3.0 `_compute_eligibility()` verbatim against the 168 tracts' published
  metrics returns eligible for 168 of 168 — but only on the assumption that the
  retired workbook exposed a column that `ELIGIBILITY_FILE_COLUMNS` mapped to
  `is_non_metro`. Without one, the same function returns eligible for 0 of 168,
  and that assumption cannot now be checked.

- **`DEEP_AMI_THRESHOLD` 0.50 → 0.40 and `DEEP_UNEMPLOYMENT_MULTIPLIER` 2.0 →
  2.5.** The shipped values were more permissive than the CDFI Fund's
  definition and would classify tracts as deeply distressed that the Fund does
  not. The Fund's own NOTES sheet, row *"Column P. Deep Distress"*, reads
  `Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)` — the same
  string this package has carried as the column-15 header pin since 0.4.0. The
  package held the correct definition in one place and the wrong one in another.

  Corroborated empirically, and the measurement has to name its file.
  `LIC AND (poverty>40% OR MFI<=40% OR unemployment ratio>=2.5)` reproduces the
  published deep-distress flag with **zero mismatches across all 85,395 rows of
  the Aug-2025b file**, reading LIC from column C alone. That zero does **not**
  survive the July-2026 re-publish: the Fund widened column C without
  recomputing columns O/P, so against the live file the same rule mismatches on
  **3** deep rows — and 20 severe — every one of them among the 168 (see Notes).
  The rule did not get worse; the Fund's published flags stopped agreeing with
  the Fund's published LIC column.

  For scale on the live file: this pair misses 3 deep rows. Substituting the
  0.4.1 thresholds (MFI≤50%, ratio≥2.0) while keeping the corrected 5.4%
  divisor misses 5,025. The 0.4.1 release as actually shipped — those
  thresholds *and* the 5.7% divisor — misses 4,420. No prong is redundant:
  dropping the poverty term alone costs 1,183 rows, the MFI term 1,244, the
  unemployment term 2,839.

- **`NATIONAL_UNEMPLOYMENT_RATE` 0.057 → 0.054.** The Fund's NOTES sheet, row
  *"Column L"*: *"the ratio between the census tract unemployment rate and the
  national unemployment rate, which is 5.4 percent."* Measured on the live file:
  column H ÷ column L rounds to 5.400000 at six decimal places for all 82,107
  rows with a non-zero ratio (observed range 5.3999997 to 5.4000003, largest
  deviation 3.1e-07). This is float division of two published, rounded columns,
  so it is not bit-exact — 2,346 of the 82,107 quotients equal 5.4 exactly. 5.7%
  raised the bar on every unemployment-prong distress comparison.

  **Scope of the three constant fixes:** the live `.xlsb` path reads the Fund's
  pre-computed LIC / severe / deep flags and does not consult these constants,
  so no live verdict changes. They are used by `_compute_eligibility()`, which
  backs `load_sample_table()` / `NMTCMapper.from_sample()`; 2 of the 12
  synthetic sample tracts move `deep` → `severe`. They are also exported and
  documentable, and a future feature would compute from them. Nothing outside
  this repo recomputes them — nmtc-screener consumes LIC status as an input and
  the nmtc-eligibility skill quotes no thresholds.

- **`EligibilitySchemaError` now explains itself.** It previously reported only
  the column index and the expected-vs-actual strings, which says what broke but
  not what to do. It now also states that the CDFI Fund re-publishes in place at
  the same URL, that this package pins exact headers deliberately, and that the
  remedy is to upgrade or to report the mismatch. It deliberately offers **no
  bypass** — there isn't a safe one, because continuing past an unrecognized
  header means reading eligibility out of an unverified column.

### Notes
- The re-published workbook **drops the `High migration tracts` sheet** present
  in the Aug-2025b release (3 sheets → 2). The loader reads only the `2016-2020`
  sheet, so nothing breaks — but that sheet was the file's only prose
  explanation of the §45D(e)(5) route, and it held both the 168-tract list and
  the 520-county high-migration list. The NOTES sheet's Column N entry still
  ends *"A list of these qualifying census tracts is below"*, now pointing at a
  sheet that no longer exists.
- The Fund did **not** recompute columns O/P after widening column C. 20 tracts
  now satisfy the published severe-distress definition while being published
  `NO`, and 3 do so for deep distress — all of them among the 168. This package
  reports the Fund's published flags as-is and does not second-guess them; the
  discrepancy is pinned by a live test so it cannot grow unnoticed.
- **The workbook's NOTES sheet and its data sheet disagree on the column-C
  header.** NOTES spells it *"…or Rural High Migration Census Tract?"*; the data
  sheet's own header row — the string the loader pins and compares against —
  reads *"…or High Migration Rural Census Tract?"*. The data sheet is
  authoritative; a note beside the pins in `schema.py` now says so, because
  refreshing the pins from NOTES would produce a string that has never appeared
  in the data and would fail every live load.
- **Two tracts appear to be under-included upstream.** Presque Isle County, MI
  (26141) is on the Fund's published high-migration county list and has three
  column-N `YES` tracts, but tracts 26141950100 (MFI 0.8136) and 26141950500
  (MFI 0.8416) sit inside the ≤85% band, qualify on no other prong, and are
  published `NO` in both column C and column N — in the Aug-2025b file and in
  the July-2026 re-publish alike. They are the only two such tracts in the
  entire 520-county high-migration universe. This package reports the Fund's
  published flags and does not add tracts the Fund omits, so nmtc-mapper returns
  `nmtc_eligible=False` for both. Recorded here because it is the one place the
  published data and the plain reading of §45D(e)(5) appear to diverge.

## [0.4.1] — 2026-07-17

Geocoder vintage alignment — the Connecticut correctness fix.

### Fixed
- **Connecticut addresses no longer fail to resolve.** The geocoder sent
  `vintage=Current_Current`, which tracks the newest TIGER release, while the
  CDFI Fund eligibility table is frozen on **2020 census tracts** (its column-0
  header: "2020 Census Tract Number FIPS code. GEOID"). The two had **drifted
  apart**. When the Census Bureau replaced Connecticut's eight legacy counties
  with nine COG/planning regions (effective with the 2022 ACS), addresses in CT
  began geocoding to COG-based GEOIDs (county FIPS `0911x`–`0919x`) that do not
  exist in the table — the county FIPS is the middle five digits of every tract
  GEOID, so the join could not match. The CDFI Fund continues to use the legacy
  county data for Connecticut (NMTC LIC ACS FAQ, Feb 1 2024, General Q4).

  Effect of the drift: on **0.4.0**, every Connecticut address returned
  `not-found` (indeterminate). On **0.1.0–0.3.4**, before the tri-state fix, the
  same drift produced a fabricated **"ineligible"** verdict for real Connecticut
  tracts. **883 Connecticut tracts (316 eligible)** were affected.

  Example: `765 Asylum Ave, Hartford, CT` geocoded to `09110524600` (Capitol
  Planning Region), absent from the table. It now geocodes to `09003524600`
  (same tract, legacy Hartford County), which is in the table and NMTC-eligible.

- **The fix: `vintage=Census2020_Current`.** The address benchmark stays
  `Public_AR_Current` — current address ranges, so newly built addresses still
  geocode — resolved onto **2020** tract geography, which is what the table
  carries. `Census2020_Census2020` was rejected (it would pin the address
  benchmark to 2020 and fail to geocode anything built since); `Census2010` was
  rejected (it returns 2010 tracts, which the 2020-tract table does not carry —
  e.g. Seattle would return the pre-split `53033007100`).

### Changed
- **Tract basis and geocoder vintage are now bound in one structure**
  (`schema.TRACT_VINTAGE`, a frozen `TractVintage`). Both the loader (which
  validates the downloaded table's column-0 header) and the geocoder (which
  sends `benchmark`+`vintage`) read this single object — not two constants in
  two modules that a future edit could desync. `TractVintage.__post_init__`
  refuses to construct a binding whose geocoder vintage, table header, and basis
  year disagree, so this class of drift cannot silently return. When the CDFI
  Fund ships the 2021-2025 ACS table on a new tract vintage, this one object
  moves and both consumers move with it.
- Sync and async geocoder paths both build their request through the one
  `_geocoder_params` helper, so neither can drift from the table or each other.
- `pyproject.toml`: `authors` metadata added; `live` pytest marker registered so
  network smoke tests are deselected in CI (`-m "not live"`).

### Recon (reported, not acted on)
- Enumerated every county FIPS in the table's 85,395 GEOIDs against the Census
  Bureau's current (2024) county universe. **Connecticut is the only drifted
  state**: the 8 legacy CT counties (`09001`–`09015`) are the only table county
  FIPS that no longer exist, and the 9 CT planning regions (`09110`–`09190`) are
  the only current county FIPS absent from the table. No other state is affected
  this cycle.

### Known Issues
- **`is_opportunity_zone` is unreliable — a `False` may be a vintage miss, not a
  real "not an OZ".** This is a *second* vintage-mismatched join, in a different
  field, of the same class as the Connecticut bug — and it is **pre-existing**:
  0.4.1 neither causes nor worsens it (both `Current_Current` and the new
  `Census2020_Current` return non-2010 tracts, so neither ever aligned with the
  2010-based OZ list).

  The Opportunity Zone list is loaded from the CDFI Fund's Dec 2018 designated-
  QOZ file (`designated-qozs.12.14.18.xlsx`). Opportunity Zones were designated
  in 2018 on **2010 census tracts**, and the designation is legally fixed to
  those tracts. Verified against the Census 2010↔2020 tract crosswalk: **all
  8,764 OZ GEOIDs are 2010 tracts**. The geocoder now returns **2020** tracts,
  and **1,408 of the 8,764 OZ designations (~16%)** have no matching GEOID in the
  2020 tract universe (they split, merged, or were renumbered between 2010 and
  2020). `is_opportunity_zone` compares a 2020 GEOID against the 2010-based list,
  so an address in one of those 1,408 designations reports **"Opportunity Zone:
  No"** — a fabricated negative.

  Interpretation: a **`Yes` is trustworthy** (the GEOID matched a designated OZ);
  a **`No` is not** — it may mean "not an OZ" *or* "OZ designation with no 2020
  GEOID," and the package cannot currently distinguish the two.

  Not fixed here. The honest fix makes `is_opportunity_zone` tri-state
  (`Optional[bool]`: `True` on match, `None` on a vintage miss — a real "no" is
  not knowable from this join), a breaking contract change slated for **0.5.0**,
  together with a design decision about geocoding at two vintages.

- **`is_nmtc_native_area` is always `False` — a `False` means "not determined,"
  not "not a native area."** Verified: the field is `False` for **all 85,395
  tracts** (zero `True`). **No data source in this package populates it.** The
  live CDFI Fund file is the `.xlsb` LIC eligibility table, whose 16 columns
  contain no native-area field; the `.xlsb` loader hardcodes `False`, and the
  only mapping that could set it (`"NATIVE_AREA"`) lives on the `.xlsx` branch
  the live URL never takes. The field is structurally incapable of being `True`.

  This is a real NMTC criterion the package cannot see, not a fabricated one.
  Native areas — Federal Indian Reservations, Off-Reservation Trust Lands,
  Hawaiian Home Lands, and Alaska Native Village Statistical Areas — are a
  documented NMTC **Areas of Higher Distress** criterion in the CDFI Fund's NMTC
  allocation application / Native Initiative materials, a **separate** CDFI Fund
  publication this package does not load (the LIC ACS FAQ, Feb 1 2024, Q6 points
  such criteria to the Compliance & Monitoring materials, not the LIC file). So a
  `False` here should be read as "this package did not determine native-area
  status," never as "confirmed not a native area."

  Pre-existing since **0.1.0**; 0.4.1 neither causes nor changes it. Resolution
  deferred to **0.5.0** — populate from the real source (needs recon), drop the
  field (breaking), or make it `Optional[bool]` with `None` (breaking).

## [0.4.0] — 2026-07-16

Fail-loud + tri-state eligibility. **This release contains breaking changes** —
functions that used to return a value now raise, and `nmtc_eligible` becomes
`Optional[bool]`. Per 0.x semver, breaking changes ship in a minor.

### Breaking
- **`nmtc_eligible` is now tri-state `Optional[bool]`.** `True` = verified
  eligible, `False` = verified ineligible (the table explicitly says NO),
  `None` = **INDETERMINATE** (geocode no-match, or a tract absent from the
  ~85k-tract universe). A `None` verdict must never be read as a falsy
  "ineligible" — an indeterminate result rendered as `False` is a fabricated
  VERIFIED INELIGIBLE. `distress_level` gains a `"unknown"` value and
  `EligibilityResult` gains a `tract_found` field and an `eligibility_status`
  property (verified-eligible / verified-ineligible / not-found / geocode-failed).
- **The geocoder no longer collapses every failure into `None`.**
  `geocode_address` (and the async `_geocode_single_async`) now:
  - raise `GeocoderTransportError` on transport/HTTP-status/decode failure after
    retries (403 / 5xx / timeout / connection / bad-JSON, each with a
    distinguishable message naming the address);
  - raise `AmbiguousAddressError` when an address matches multiple **different**
    census tracts (matches that all agree on one tract still succeed);
  - return `None` **only** for a genuine no-match (HTTP 200, zero matches).
- **`check_tract` / `check_address` lookup-miss now indeterminate.** An absent
  tract yields `nmtc_eligible=None`, `distress_level="unknown"`, metrics `None`,
  `tract_found=False` — not `False`/`"ineligible"`. `check_address` on a genuine
  geocode no-match yields the same with `geocode_success=False`; typed geocoder
  errors propagate rather than being swallowed into a result.
- **`enrich_dataframe` carries the tri-state** (absent tract → `None`/`"unknown"`,
  not `False`) and adds an additive `eligibility_status` column. `eligible_count`
  no longer counts indeterminate rows as ineligible and reports an
  `indeterminate` tally.

### Added
- **New typed exceptions, all under `NMTCMapperError`:**
  `EligibilitySchemaError`, `EligibilityValueError`, `GeocoderError` →
  {`GeocoderTransportError`, `AmbiguousAddressError`}.
- **Schema validation at load (.xlsb path).** Before any row is trusted the
  loader checks the column count (16), the header strings at every
  positionally-bound index (normalized: whitespace-collapsed, casefolded), and a
  row-count floor — raising `EligibilitySchemaError` naming the offending index,
  expected, and actual. The positional bind can no longer read a poverty rate out
  of the MFI slot silently.
- **Value plausibility bounds.** Parsed numerics are range-checked against bounds
  derived from all 85,395 live rows: `poverty_rate` and `unemployment_rate`
  (stored ÷100) in `[0, 1]`; `ami_ratio` (stored as a FRACTION) in `[0, 10]` — the
  upper bound clears the real max (5.162) yet trips an upstream percent-scale flip
  (0.9127 → 91.27), a silent 100× error in every AMI comparison. An `'NA'` cell
  remains a legitimate null and is never bounds-checked.
- **`LICENSE`** (MIT) added.

### Fixed
- `summary()` renders an indeterminate result distinctly (inline qualifier on the
  NMTC Eligible line) instead of the fabricated `❌ NO`.
- `loader.py` module docstring corrected: the table is the FULL universe
  (35,167 eligible + 50,228 ineligible), not "all eligible census tracts".
- **Async batch geocoding was 100% broken and is now fixed (C-1).**
  `_batch_geocode_async` wrapped every coroutine in `create_task` inside an
  `as_completed` loop that discarded the results, then `gather()`-ed the same
  coroutine objects — re-awaiting an already-driven coroutine raised
  `RuntimeError: cannot reuse already awaited coroutine`. Every
  `enrich(address_col=)` / `geocode_batch(use_async=True)` call on ≥2 addresses
  raised. Each coroutine is now awaited exactly once via a single `gather`.
- **A geocoder error aborts the whole batch.** `_batch_geocode_async` calls
  `gather` **without** `return_exceptions`, so a transport/ambiguity failure in
  any one address raises its typed `GeocoderError` and aborts the entire batch.
  This is deliberate, not a regression: it replaces the pre-0.4.0 silent per-row
  `None`, which downstream became a fabricated **verified-ineligible**. Losing
  time to a re-run is strictly better than losing truth. This is not a feature —
  per-row failure capture (continue the batch, mark only the failed rows
  indeterminate) is planned for **0.4.1**.
- **No `nest_asyncio`.** `geocode_batch` previously reached for `nest_asyncio`
  when called inside a running event loop (e.g. Jupyter) — an **undeclared
  dependency** absent from `Requires-Dist`, working only off an ambient install.
  It now detects a running loop and falls back to the synchronous path with a
  `RuntimeWarning` (identical results, only slower); no new dependency.
- **`EligibilityResult.eligibility_status` no longer fabricates
  `verified-ineligible` for an indeterminate result (M-4).** With
  `nmtc_eligible=None` and `tract_found` defaulted `True`, the property fell
  through its falsy branch and returned `verified-ineligible`; it now guards
  `is None` first, as `summary()` already did.

## [0.3.4] — 2026-07-11

### Fixed — fail loud, never fabricate (this is a correctness release)
- **Silent sample-data substitution removed from every failure path.** In
  0.1.0–0.3.3 the loader silently substituted a 12-tract synthetic sample dataset
  on ANY eligibility download or parse failure, and a 6-tract OZ sample on ANY OZ
  download or parse failure. Results computed in that state were **fabricated** —
  an eligibility check against a real tract could return a false "ineligible"
  (the tract simply wasn't in the 12-row sample), and no signal ever reached the
  caller. Five distinct fabrication paths are now killed:
  1. eligibility download failure (`loader.py` download step) — was `return None`
     → 12-tract sample; now raises `EligibilityDownloadError`.
  2. eligibility missing-file / download-skipped branch — was 12-tract sample;
     now raises `EligibilityDownloadError`.
  3. eligibility parse failure (corrupt bytes, HTML error page, bad zip) — was
     12-tract sample; now raises `EligibilityParseError`.
  4. OZ download failure — was 6-tract sample; now raises `OZDownloadError`.
  5. OZ parse failure (corrupt file **or** missing tract column) — was 6-tract
     sample; now raises `OZParseError`.

### Added
- **Typed exception hierarchy** (`nmtcmapper/exceptions.py`), exported from the
  package top level:
  `NMTCMapperError` → `EligibilityDataError` → {`EligibilityDownloadError`,
  `EligibilityParseError`}, and `OZDataError` → {`OZDownloadError`,
  `OZParseError`}. Messages name the URL attempted and distinguish access-blocked
  (403 / connection / DNS / timeout) from not-found (404) from parse failure, and
  chain the original exception (`raise ... from e`). Catch at any level:
  `except NMTCMapperError` for anything, or a specific leaf.
- **Explicit sample mode.** `_build_sample_table()` is promoted to the public
  `load_sample_table()` (the underscore name is kept as an alias for the existing
  notebook import), and `NMTCMapper.from_sample()` constructs a mapper on the 12
  sample tracts + 6 OZ sample tracts with **zero network calls**. Sample data is
  now an opt-in demo path only — never a runtime fallback.
- **Provenance marker.** Every mapper carries a `data_source` attribute
  (`"cdfi_fund"` for the real constructor, `"sample"` for `from_sample()`),
  surfaced in `repr(mapper)`, so downstream code can assert it never shipped a
  demo answer as real.

### Known issues
- **Fabrication moves downstream, not gone from the ecosystem.** The flagship
  `nmtc-application-builder` adapter (`nmtc_mapper_adapter.py`) wraps mapper
  construction in a bare `except Exception` and substitutes its own 20-tract
  `_FALLBACK_ELIGIBILITY`. Now that this package raises typed errors instead of
  fabricating, that adapter will catch them and fabricate in its place — until
  the adapter is fixed in a separate cycle (catch the typed errors, surface them
  honestly, and remove both the `redirect_stdout` suppression and the
  geocode-failure fabricated-positive). No change is made to that repo here.

  > **Correction (0.4.0, 2026-07-16):** the claim above that the flagship adapter
  > "will catch them and fabricate in its place" was true only *before* the
  > adapter's 1.1.5 release. As of `nmtc-application-builder` 1.1.5 the adapter no
  > longer fabricates — it catches the typed errors and surfaces them honestly,
  > and the `redirect_stdout` suppression and geocode-failure fabricated-positive
  > are gone. The note above is retained for history but **no longer describes
  > current behavior**; it should not be read as an ongoing accusation against a
  > package that is already fixed.
- **Out of scope, deferred to 0.3.5:** the geocoder failure-swallow in
  `geocoder/census.py`, and schema/column-shift validation of the CDFI Fund file.
  A geocode failure or an unknown/malformed tract ID still returns a normal result with
  `nmtc_eligible=False` / `distress_level="ineligible"` rather than raising — only
  `geocode_success=False` distinguishes it, and `enrich()` output carries no such flag.
  Treat "ineligible" as unverified unless `geocode_success` is True and the tract was found.

  > **Resolved (0.4.0):** both were fixed in 0.4.0, not 0.3.5 — the geocoder now
  > raises typed `GeocoderTransportError` / `AmbiguousAddressError`, a lookup miss
  > is `None`/`"unknown"` (never `False`/`"ineligible"`), and `enrich()` carries an
  > `eligibility_status` column.

## [0.3.3] — 2026-06-23

> **Correction (2026-07):** the "publishes to PyPI via an OIDC Trusted Publisher" line in the
> 0.3.3 entry below described the *intended* pipeline; 0.3.3 was actually published manually
> with twine, no attestations. The OIDC pipeline first runs for 0.3.4.

### Changed
- **`__version__` is now derived from installed package metadata** via
  `importlib.metadata.version("nmtc-mapper")` instead of a hardcoded string.
  This fixes a drift where the shipped wheel reported `__version__ == "0.1.0"`
  while the distribution had been bumped to `0.3.2` — `pyproject.toml` is now
  the single authoritative source of the version.
- **`setup.py` reduced to a build shim** — the stale `version="0.3.0"` pin and
  the duplicate dependency list were removed; all metadata now lives in
  `pyproject.toml`.

### Added
- **CI / release infrastructure** — `ci.yml` (test matrix on Python 3.9–3.12,
  all actions SHA-pinned) and a tag-triggered `release.yml` that verifies the
  tag matches `pyproject.toml`, builds the wheel, tests the installed wheel in a
  fresh venv, and publishes to PyPI via an OIDC Trusted Publisher (no API token).

No behavioral or API change — this is a hygiene-only release.

## [0.3.2] — 2026-05-14

### Fixed
- **OZ download URL** — The original URL (`cdfifund.gov/sites/cdfi/files/2018-06/
  QOZ_Tracts_List_Formatted_July2018.xlsx`) returned HTTP 404, causing every
  cold install to fall back to a 6-tract sample and flag no real project as an
  Opportunity Zone.  Updated to the canonical CDFI Fund file at
  `cdfifund.gov/system/files/documents/designated-qozs.12.14.18.xlsx`.
- **OZ xlsx parse logic** — The new file uses sheet name `"QOZs 14Jun"`, has a
  preamble so the actual column header is on row 5 (index 4), and names the
  tract column `"Census Tract Number"` rather than `"GEOID"` / `"TRACT"`.
  Updated `load_opportunity_zones()` to pass `sheet_name` and `header=4`, and
  added `"CENSUS TRACT NUMBER"` as the first candidate in the column search.
- **openpyxl floor raised to `>=3.1.0`** — current pandas requires this minimum
  to read the OZ xlsx; the previous floor of `>=3.0.0` allowed installs that
  silently failed to parse the file.

## [0.3.1] — 2026-05-14

### Fixed
- **CDFI Fund download URL** — The Aug 2025 CDFI Fund site update moved the
  NMTC eligibility file to a new path and changed the format from `.xlsx` to
  `.xlsb`. The previous URL returned HTTP 404, causing every fresh install to
  silently fall back to the 12-tract sample dataset and classify all real tracts
  as ineligible.

### Added
- **`.xlsb` format support** — Added `pyxlsb>=1.0.0` as a dependency and a new
  `_load_xlsb_table()` parser in `data/loader.py`. The loader now detects file
  format by extension and routes accordingly; the legacy `.xlsx` path is
  preserved as a fallback.
- **CDFI Fund pre-computed distress flags** — The Aug 2025 file ships its own
  `Severe distress` and `Deep distress` YES/NO columns computed by CDFI Fund
  staff. `_load_xlsb_table()` reads these directly instead of recomputing from
  raw thresholds, keeping classification consistent with official CDFI Fund
  determinations.

## [0.3.0] — 2025-04-XX

- Added Opportunity Zone overlay flag (`is_opportunity_zone`) on all results.
- 27/27 tests passing.

## [0.2.1] — 2025-XX-XX

- Published to PyPI.

## [0.2.0] — 2025-XX-XX

- Initial public release with `check_tract`, `check_address`, and `enrich`.
