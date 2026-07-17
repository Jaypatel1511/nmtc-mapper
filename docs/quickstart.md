# Quickstart

## Basic Usage

    from nmtcmapper import NMTCMapper

    mapper = NMTCMapper()

    result = mapper.check_address("1234 S Michigan Ave, Chicago, IL 60605")
    result.summary()

    result = mapper.check_tract("17031840100")
    print(result.nmtc_eligible)
    print(result.distress_level)

## Batch Processing

    import pandas as pd

    df = pd.read_csv("projects.csv")
    df = mapper.enrich(df, address_col="address")
    print(df["nmtc_eligible"].value_counts())
    mapper.eligible_count(df)

## Using Existing Tract IDs

    df = mapper.enrich(df, tract_col="tract_id")

## Output Columns

| Column | Type | Description |
|--------|------|-------------|
| nmtc_eligible | Optional[bool] | True (eligible) / False (verified ineligible) / None (indeterminate — never read None as "ineligible") |
| eligibility_status | str | verified-eligible / verified-ineligible / not-found / geocode-failed |
| distress_level | str | deep / severe / lic / ineligible / unknown (unknown = indeterminate) |
| poverty_rate | Optional[float] | Census tract poverty rate (None if indeterminate) |
| ami_ratio | Optional[float] | MFI as pct of area median income (None if indeterminate) |
| unemployment_rate | Optional[float] | Census tract unemployment rate (None if indeterminate) |
| severe_distress | bool | CDFI Fund severe-distress designation (read from the official file) |
| deep_distress | bool | CDFI Fund deep-distress designation (read from the official file) |
