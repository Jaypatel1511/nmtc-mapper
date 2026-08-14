# API Reference

## NMTCMapper

    from nmtcmapper import NMTCMapper
    mapper = NMTCMapper(force_reload=False)

### check_address(address)
Geocode a single address and return eligibility result.

### check_tract(tract_id)
Check eligibility for a known 11-digit FIPS code.

### enrich(df, address_col, tract_col, batch_size)
Add eligibility columns to a DataFrame.

### eligible_count(df)
Print and return eligibility summary statistics. Returns a dict of nine keys:
`total`, `determined`, `nmtc_eligible`, `pct_eligible_of_determined`,
`deep_distress`, `severe_distress`, `lic_only`, `ineligible`, `indeterminate`.

`pct_eligible_of_determined` divides by `determined` (`nmtc_eligible +
ineligible`), not by `total`, and is `None` when `determined == 0`. The 0.4.3 key
`pct_eligible` was removed rather than redefined, so `out["pct_eligible"]` raises
`KeyError`.

## EligibilityResult

| Attribute | Type | Description |
|-----------|------|-------------|
| address | str | The address or tract id the check was made for |
| tract_id | Optional[str] | 11-digit FIPS code (None if no tract resolved) |
| nmtc_eligible | Optional[bool] | Tri-state: True / False / None (None = indeterminate, never falsy "ineligible") |
| eligibility_status | str | verified-eligible / verified-ineligible / not-found / geocode-failed |
| distress_level | str | deep / severe / lic / ineligible / unknown |
| poverty_rate | Optional[float] | Tract poverty rate. **Two null states** — see below |
| ami_ratio | Optional[float] | MFI/AMI ratio. **Two null states** — see below |
| unemployment_rate | Optional[float] | Tract unemployment rate. **Two null states** — see below |
| is_non_metro | Optional[bool] | Non-metropolitan designation; None on the two indeterminate branches |
| is_high_migration_rural | Optional[bool] | High-migration-rural-county designation; None on the two indeterminate branches |
| severe_distress | Optional[bool] | Severe-distress designation; None on the two indeterminate branches |
| deep_distress | Optional[bool] | Deep-distress designation; None on the two indeterminate branches |
| is_opportunity_zone | Optional[bool] | **True or None, never False.** True when the GEOID is on the Dec-2018 designation list. See `opportunity_zone_status` |
| geocode_success | bool | "No unresolved address stands between this result and its tract" — `check_tract()` sets it True with no geocoding performed. Stays a plain bool |
| tract_found | bool | Whether the tract was present in the eligibility universe. Stays a plain bool |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| distress_description | str | Human-readable expansion of `distress_level` |
| opportunity_zone_status | str | designated / not-confirmed / no-tract. Switch on this, never on the truthiness of `is_opportunity_zone` |

### The tri-state booleans

`is_non_metro`, `is_high_migration_rural`, `severe_distress` and `deep_distress`
became `Optional[bool]` in 0.5.0. **A found tract's `False` is unchanged** — it is
the CDFI Fund's published `NO`. `None` appears only where no row was read: the
tract is absent from the table, or geocoding resolved no tract.

`is_opportunity_zone` is different: it is `Optional[bool]` on **every** path and
is never `False`. The 2018 designations are 2010-tract-based while this table and
geocoder are 2020-basis, so a non-match and a genuine non-designation are the same
observation. Its membership test is keyed on the designation set and **not** on
`tract_found`, so a retired 2010 GEOID that was designated still returns `True`
alongside `tract_found=False`.

### The three metrics have two distinct null states

| Value | Means | `summary()` prints |
|-------|-------|--------------------|
| `None` | The tract was never read — absent from the table, or geocoding resolved no tract | `❓ UNKNOWN — tract not read` |
| `NaN` | The tract **was** found and the CDFI Fund published no value for this metric (`NA` in the source file). These tracts still carry a real published YES/NO eligibility verdict | `not available — the CDFI Fund published no value for this tract` |

1,583 found tracts carry a null poverty rate and 2,358 a null AMI ratio; 2,750
distinct tracts carry at least one. `r.poverty_rate is None` is therefore **not** a
missing-value test on this field — `NaN is not None` is `True`. Use
`pd.isna(r.poverty_rate)` for "no number available either way", and
`eligibility_status` to tell which kind of missing you have.

### Removed in 0.5.0

`is_nmtc_native_area` is gone — reading it raises `AttributeError`, passing it to
the constructor raises `TypeError`, and `df["is_nmtc_native_area"]` after
`.enrich()` raises `KeyError`. It was never obtainable: the CDFI Fund publishes no
tract-keyed NMTC native-area resource, and AIANNH entities carry four-digit GEOIDs
that cannot nest into `SSCCCTTTTTT`. Dropping it fails loud where a tri-state
would have failed silent.
