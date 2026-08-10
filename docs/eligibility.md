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
| Median Family Income (rural) | <= 85% of state AMI |

## Distress Levels

| Level | Poverty | AMI | Unemployment |
|-------|---------|-----|--------------|
| Deep | > 40% | <= 40% | >= 2.5x national |
| Severe | > 30% | <= 60% | >= 1.5x national |
| LIC | >= 20% | <= 80% | — |
| Ineligible | < 20% | > 80% | — |

The severe and deep rows are OR-ed internally and AND-ed with LIC. They are the
CDFI Fund's criteria, quoted from the eligibility workbook's own column-14 and
column-15 headers and restated in Q32 of the Fund's *NMTC Compliance Monitoring
and Evaluation Frequently Asked Questions* (updated April 2025).

Note the poverty column changes comparison between rows, and that is correct:
LIC is **at least** 20% (§45D(e)(1)(A) — "a poverty rate of at least 20
percent"), while severe and deep are **strictly greater** than 30% and 40% (the
Fund's headers read `Poverty>30%` and `Poverty>40%`; FAQ Q32 says "greater than
40%"). Of the LIC tracts at exactly 30.0% poverty qualifying on that prong
alone, the Fund published `severe = NO` for all 21; at exactly 40.0%,
`deep = NO` for all 13.
