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
| nmtc_eligible | bool | NMTC eligibility flag |
| distress_level | str | deep/severe/lic/ineligible |
| tract_id | str | 11-digit FIPS code |
| poverty_rate | float | Tract poverty rate |
| ami_ratio | float | MFI/AMI ratio |
| geocode_success | bool | Whether geocoding succeeded |
