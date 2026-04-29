# nmtc-mapper 🗺️

**Automated NMTC eligibility checker for addresses and census tracts.**

Pass a DataFrame of addresses and get back a boolean column for NMTC eligibility,
distress level, poverty rate, AMI ratio, and more — using official CDFI Fund and
Census Bureau data. No manual lookups required.

---

## Why nmtc-mapper?

The CDFI Fund provides a manual web tool (CIMS) for checking NMTC eligibility
one address at a time. nmtc-mapper automates this — pass 10,000 addresses and
get results in seconds, using the same official data source.

---

## Installation

    pip install nmtc-mapper

---

## Quickstart

    from nmtcmapper import NMTCMapper

    mapper = NMTCMapper()

    # Single address (geocodes automatically)
    result = mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")
    result.summary()
    print(result.nmtc_eligible)    # True
    print(result.distress_level)   # "severe"
    print(result.poverty_rate)     # 0.38

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

## Eligibility Rules (2016-2020 ACS — mandatory since Sept 1, 2024)

A census tract qualifies as a Low-Income Community (LIC) if it meets ANY of:

- Poverty rate >= 20%
- Median Family Income <= 80% of metro/state AMI
- Median Family Income <= 85% of state AMI (high migration rural counties)

Distress levels:

- deep     — Poverty >= 40% OR AMI <= 50% OR unemployment >= 2x national rate
- severe   — Poverty >= 30% OR AMI <= 60% OR unemployment >= 1.5x national rate
- lic      — NMTC eligible (meets LIC criteria)
- ineligible — Does not qualify

---

## Data Sources

- CDFI Fund 2016-2020 ACS Low-Income Community Eligibility File
  https://www.cdfifund.gov/research-data
- US Census Bureau Geocoding API (free, no API key required)
  https://geocoding.geo.census.gov

---

## Output Columns

After running .enrich(), your DataFrame will have:

- nmtc_eligible (bool)
- distress_level (str: deep / severe / lic / ineligible)
- poverty_rate (float)
- ami_ratio (float)
- unemployment_rate (float)
- is_non_metro (bool)
- severe_distress (bool)
- deep_distress (bool)

---

## Running Tests

    PYTHONPATH=. pytest tests/ -v

24 tests across all modules.

---

## Who This Is For

- CDEs screening project locations for NMTC eligibility
- CDFI analysts qualifying borrower locations at scale
- Researchers analyzing geographic distribution of LIC tracts
- Anyone replacing manual CIMS lookups with automated Python

---

## License

MIT 2026 Jaypatel1511
