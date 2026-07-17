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
Print and return eligibility summary statistics.

## EligibilityResult

| Attribute | Type | Description |
|-----------|------|-------------|
| nmtc_eligible | Optional[bool] | Tri-state: True / False / None (None = indeterminate, never falsy "ineligible") |
| eligibility_status | str | verified-eligible / verified-ineligible / not-found / geocode-failed |
| distress_level | str | deep / severe / lic / ineligible / unknown |
| tract_id | Optional[str] | 11-digit FIPS code (None if no tract resolved) |
| poverty_rate | Optional[float] | Tract poverty rate (None if indeterminate) |
| ami_ratio | Optional[float] | MFI/AMI ratio (None if indeterminate) |
| geocode_success | bool | Whether geocoding succeeded |
| tract_found | bool | Whether the tract was present in the eligibility universe |
