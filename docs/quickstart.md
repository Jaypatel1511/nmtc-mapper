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
| nmtc_eligible | bool | True if tract qualifies as LIC |
| distress_level | str | deep / severe / lic / ineligible |
| poverty_rate | float | Census tract poverty rate |
| ami_ratio | float | MFI as pct of area median income |
| unemployment_rate | float | Census tract unemployment rate |
| severe_distress | bool | True if severe distress criteria met |
| deep_distress | bool | True if deep distress criteria met |
