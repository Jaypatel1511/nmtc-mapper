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

`.enrich()` adds **ten** columns:

| Column | Type | Description |
|--------|------|-------------|
| nmtc_eligible | Optional[bool] | True (eligible) / False (verified ineligible) / None (indeterminate — never read None as "ineligible") |
| eligibility_status | str | verified-eligible / verified-ineligible / not-found / geocode-failed |
| distress_level | str | deep / severe / lic / ineligible / unknown (unknown = indeterminate) |
| poverty_rate | Optional[float] | Census tract poverty rate. **Two null states** — see below |
| ami_ratio | Optional[float] | MFI as pct of area median income. **Two null states** — see below |
| unemployment_rate | Optional[float] | Census tract unemployment rate. **Two null states** — see below |
| is_non_metro | Optional[bool] | CDFI Fund non-metropolitan designation; None on the indeterminate branches |
| is_high_migration_rural | Optional[bool] | CDFI Fund high-migration-rural-county designation; None on the indeterminate branches |
| severe_distress | Optional[bool] | CDFI Fund severe-distress designation (read from the official file); None on the indeterminate branches |
| deep_distress | Optional[bool] | CDFI Fund deep-distress designation (read from the official file); None on the indeterminate branches |

### The four tri-state booleans

`nmtc_eligible`, `is_non_metro`, `is_high_migration_rural`, `severe_distress` and
`deep_distress` are `Optional[bool]` as of 0.5.0. **A found tract's `False` is
unchanged** — it is the Fund's published `NO`. `None` appears only on the two
indeterminate branches (tract absent from the table, or geocoding resolved no
tract), where nothing was read at all.

Because `None` is falsy, `~df["severe_distress"]` now raises `TypeError` on a
frame containing indeterminate rows, and a truthiness gate would fold them into
"not severe". Filter explicitly: `df["severe_distress"] != True`.

### The three metrics have two distinct null states

They are not interchangeable and the package renders them with different words:

| Value | Means | `summary()` prints |
|-------|-------|--------------------|
| `None` | The tract was never read — absent from the table, or geocoding resolved no tract | `❓ UNKNOWN — tract not read` |
| `NaN` | The tract **was** found and the CDFI Fund published no value for this metric (`NA` in the source file). The Fund still published a YES/NO eligibility determination for these tracts | `not available — the CDFI Fund published no value for this tract` |

1,583 found tracts carry a null poverty rate and 2,358 a null AMI ratio; 2,750
distinct tracts carry at least one. Test with `pd.isna()`, which catches both —
`NaN is not None` is `True`, so an `is not None` guard silently passes NaN
through.
