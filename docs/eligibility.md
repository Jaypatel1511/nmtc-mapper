# NMTC Eligibility Rules

## Data Source

Based on the CDFI Fund 2016-2020 ACS Low-Income Community Eligibility File.
Mandatory for all QLICIs closed on or after September 1, 2024.

## Low-Income Community Criteria

A census tract qualifies if it meets ANY of the following:

| Criterion | Threshold |
|-----------|-----------|
| Poverty rate | >= 20% |
| Median Family Income (metro) | <= 80% of metro/state AMI |
| Median Family Income (high migration rural) | <= 85% of state AMI, **and** the tract must be non-metropolitan |

The 85% row needs **both** conjuncts. §45D(e)(5)(A) substitutes 85% into
§45D(e)(1)(B)**(i)** — the non-metropolitan branch — so the band cannot reach a
metropolitan tract. But §45D(e)(5)(B) defines "high migration rural county" by
out-migration alone, with no rurality and no metro test, so the designation on its
own does not carry the non-metro requirement. The shipped rule applies
`is_high_migration_rural & is_non_metro & (ami <= 0.85)`. Through 0.4.3 the rule
read `is_non_metro` *in place of* the high-migration-rural designation, which
granted LIC to **932 tracts on non-metro status alone**; the corrected rule
reproduces the Fund's published column C with 0 disagreements across all 85,395
rows. On the current file all 1,422 HMR tracts are non-metro, so the non-metro
conjunct changes no row today — it is written out because that is a property of
one published file, not of the statute.

## Distress Levels

| Level | Poverty | AMI | Unemployment |
|-------|---------|-----|--------------|
| Deep | > 40% | <= 40% | >= 2.5x national |
| Severe | > 30% | <= 60% | >= 1.5x national |
| LIC | >= 20% | <= 80% | — |
| Ineligible | < 20% | > 80% | — |

The severe and deep rows are OR-ed internally and AND-ed with LIC. They are the
CDFI Fund's criteria, quoted from the eligibility workbook's own column-14 and
column-15 headers. The **deep** criteria read identically in Q32 of the Fund's
*NMTC Compliance Monitoring and Evaluation Frequently Asked Questions* (updated
April 2025). The severe row rests on the column-14 header alone.

Note the poverty column changes comparison between rows, and that is correct:
LIC is **at least** 20% (§45D(e)(1)(A) — "a poverty rate of at least 20
percent"), while severe and deep are **strictly greater** than 30% and 40% (the
Fund's headers read `Poverty>30%` and `Poverty>40%`; FAQ Q32 says "greater than
40%"). Of the LIC tracts at exactly 30.0% poverty qualifying on that prong
alone, the Fund published `severe = NO` for all 21; at exactly 40.0%,
`deep = NO` for all 13.
