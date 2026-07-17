# 0.4.0 completion-pass evidence

Evidence round for `feat/0.4.0-fail-loud-tristate`, on top of build commit
`3c6cef7`. This is deliberately a **separate commit** so an auditor can read the
evidence apart from the build. No production or test code changed in this pass —
each mutation below was applied, its RED captured, then reverted; the working
tree is identical to `3c6cef7`. Full suite: **95 passed**.

---

## Item 1 — Fix 2 (`check_address` tri-state) has its OWN red, in `mapper.py`

`check_address`'s tri-state lives in `mapper.py`; `check_tract`'s lookup-miss
lives in `checker.py`. A `checker.py` mutation proves nothing about `mapper.py`,
so Fix 2 is mutated **independently**.

**Mutation** (mapper.py geocode-returns-None block only; `checker.py` untouched
and verified still `"nmtc_eligible": None`):

```python
tract_found=False,
nmtc_eligible=False,          # MUTANT: original 0.3.4 behavior
distress_level="ineligible",  # MUTANT
```

**RED** (`checker.py` NOT mutated during this run):

```
tests/test_tristate.py::test_check_address_no_match_is_indeterminate
>       assert res.nmtc_eligible is None              # C2
E       AssertionError: assert False is None
        EligibilityResult(... nmtc_eligible=False, distress_level='ineligible',
                          ... geocode_success=False, tract_found=False)

tests/test_constraints.py::test_c2_check_address_no_match_yields_none
>       assert res.distress_level == "unknown"
E       AssertionError: assert 'ineligible' == 'unknown'

tests/test_constraints.py::test_c2_every_unknown_distress_result_has_none_eligible  (also FAILED)
```

**Restore → GREEN:** `4 passed` (the three above + the geocoded-but-absent case).

The path was already covered; no new test was required.

---

## Item 2 — async parity, both sub-cases (evidence, not assertion)

The async path (`_geocode_single_async`) is mutated at its own sites (the sync
sites at lines 232/237 were left intact and re-confirmed present each run).

### (a) re-introduce swallow-to-None on async transport failure

**Mutation** — async `raise GeocoderTransportError(...)` → `return None`
(sync `raise` count remained `1`):

**RED:**
```
tests/test_geocoder_contract.py::test_async_403_raises_transport_error
>           _run_single(sess)
E           Failed: DID NOT RAISE nmtcmapper.exceptions.GeocoderTransportError

tests/test_geocoder_contract.py::test_async_bad_json_raises_transport_error
E           Failed: DID NOT RAISE nmtcmapper.exceptions.GeocoderTransportError
```

### (b) re-introduce the unconditional `matches[0]` pick at the async call site

**Mutation** — async `return _extract_tract_from_data(data, address)` replaced
by inline `matches[0]` extraction that bypasses ambiguity detection (sync
extractor-call count remained `1`):

**RED:**
```
tests/test_geocoder_contract.py::test_async_multi_match_different_tracts_raises
>           _run_single(sess)
E           Failed: DID NOT RAISE nmtcmapper.exceptions.AmbiguousAddressError
```

**Restore → GREEN:** async subset `5 passed`; full `test_geocoder_contract.py`
`15 passed`. Both async paths are protected; no new test was required.

---

## Item 3 — bounds recon from a FRESH download (cache bypassed)

Downloaded the live file straight from `CDFI_FUND_LIC_URL_2020` to the scratchpad
(not `~/.nmtcmapper/cache/`):

```
URL   https://www.cdfifund.gov/system/files?file=2025-08/NMTC_2016-2020_Severe_Deep_Distress_August-2025b.xlsb
HTTP  200
size  4,828,453 bytes   (Microsoft Excel 2007+)
sha256 (fresh)   09b707e899c6571ecff7f636521ae62cc3b39cef6bf8cc5c21b049c7b2b1fc12
sha256 (cached)  09b707e899c6571ecff7f636521ae62cc3b39cef6bf8cc5c21b049c7b2b1fc12   ← identical
```

**Fresh-file stats (raw, as stored) — total data rows: 85,395**

| field (col) | min | max | numeric | null / `'NA'` |
|---|---|---|---|---|
| poverty_rate (3) | 0.1 | 100.0 | 83,812 | 1,583 |
| ami_ratio (5) | 0.024946365314573667 | 5.162086747668833 | 83,037 | 2,358 |
| unemployment_rate (7) | 0.0 | 93.8 | 85,395 | 0 |

**Every figure is identical to the cached run** (the file is byte-identical). No
figure differs. The chosen bounds still hold, on the STORED value
(poverty/unemp are ÷100):

- `poverty_rate` scaled 0.001 .. 1.0 ⊂ **[0, 1]** ✓
- `unemployment_rate` scaled 0.0 .. 0.938 ⊂ **[0, 1]** ✓
- `ami_ratio` (fraction) 0.0249 .. 5.162 ⊂ **[0, 10]** ✓ (clears the real max,
  still trips a 0.9127 → 91.27 percent-scale flip)
