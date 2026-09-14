#!/usr/bin/env python3
"""0.6.1 release gate: the verdict must not move across the container change.

    scripts/verify-column-n-parity.py LEGACY_XLSB [NEW_XLSX]

Loads the superseded July-2026 `.xlsb` and the September-2026 `.xlsx` — BOTH
through the package's own container dispatch and positional parser — and
asserts, over the whole 85,395-tract universe:

  * the GEOID sets are identical;
  * `nmtc_eligible`, `distress_level`, `severe_distress`, `deep_distress`,
    `is_non_metro`, `poverty_rate`, `ami_ratio` and `unemployment_rate` are
    identical row for row;
  * `is_high_migration_rural` is True for a STRICTLY SMALLER set in the new
    file, and that set is a subset of the old one.

Exit status is non-zero on any violation. If a single verdict moves, 0.6.1 is
the wrong release: that is a methodology round, not an availability fix.

WHY A SCRIPT AND NOT A TEST. The legacy file is no longer downloadable (its URL
is a 403), so it exists only on machines that cached it before 2026-09-03. A
test that skips when the file is absent is a test that passes on every fresh
machine; a script that demands the path on its command line cannot be run
without it. The run is recorded in CHANGELOG 0.6.1.

WHY THE LEGACY PINS ARE OVERRIDDEN. The loader's header guard pins the CURRENT
headers, so the July-2026 file is (correctly) rejected by it. This script
substitutes the July-2026 strings at indices 13/14/15 for the legacy load only,
and says so. The value allowlists, bounds and row floor are NOT relaxed.
"""
import sys
from pathlib import Path

import pandas as pd

import nmtcmapper.data.loader as loader
from nmtcmapper.data.loader import _load_eligibility_workbook, _sniff_workbook_format
from nmtcmapper.data.schema import ELIGIBILITY_XLSB_EXPECTED_HEADERS

JULY_2026_HEADERS = {
    **ELIGIBILITY_XLSB_EXPECTED_HEADERS,
    13: "High Migration Rural County Low-Income Community Census Tract",
    14: "Severe distress=LIC AND (Poverty>30%; MFI<=60%;Unemployment>=1.5)",
    15: "Deep distress=LIC AND (Poverty>40%; MFI<=40%;Unemployment>=2.5)",
}

IDENTICAL = [
    "nmtc_eligible", "distress_level", "severe_distress", "deep_distress",
    "is_non_metro", "poverty_rate", "ami_ratio", "unemployment_rate",
]


def _load_with_pins(path: Path, pins: dict) -> pd.DataFrame:
    saved = loader.ELIGIBILITY_XLSB_EXPECTED_HEADERS
    loader.ELIGIBILITY_XLSB_EXPECTED_HEADERS = pins
    try:
        return _load_eligibility_workbook(path)
    finally:
        loader.ELIGIBILITY_XLSB_EXPECTED_HEADERS = saved


def main(argv) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    legacy = Path(argv[1])
    new = Path(argv[2]) if len(argv) == 3 else loader._eligibility_cache_path()
    if not new.exists():
        new = loader.download_eligibility_file()

    failures = []

    fmt_old, fmt_new = _sniff_workbook_format(legacy), _sniff_workbook_format(new)
    print(f"legacy : {legacy}  ->  container {fmt_old}")
    print(f"new    : {new}  ->  container {fmt_new}")
    if fmt_old != "xlsb":
        failures.append(f"legacy file is not an .xlsb container ({fmt_old})")
    if fmt_new != "xlsx":
        failures.append(f"new file is not an .xlsx container ({fmt_new})")

    old = _load_with_pins(legacy, JULY_2026_HEADERS)
    cur = _load_with_pins(new, ELIGIBILITY_XLSB_EXPECTED_HEADERS)

    print(f"\nuniverse        legacy {len(old):>7,}   new {len(cur):>7,}")
    only_old, only_new = old.index.difference(cur.index), cur.index.difference(old.index)
    if len(only_old) or len(only_new):
        failures.append(f"GEOID sets differ: {len(only_old)} only in legacy, "
                        f"{len(only_new)} only in new")
    common = old.index.intersection(cur.index)
    o, c = old.loc[common], cur.loc[common]

    for col in IDENTICAL:
        a, b = o[col], c[col]
        if a.dtype.kind == "f" or b.dtype.kind == "f":
            diff = ~((a == b) | (a.isna() & b.isna()))
        else:
            diff = a != b
        n = int(diff.sum())
        label = {"nmtc_eligible": "eligible", "severe_distress": "severe",
                 "deep_distress": "deep"}.get(col, col)
        if a.dtype == bool:
            print(f"{label:<17}legacy {int(a.sum()):>7,}   new {int(b.sum()):>7,}   diffs {n}")
        else:
            print(f"{label:<17}diffs {n}")
        if n:
            failures.append(f"{col}: {n} rows differ, e.g. {diff[diff].index[:5].tolist()}")

    lvl_old, lvl_new = o["distress_level"].value_counts(), c["distress_level"].value_counts()
    for k in ("deep", "severe", "lic", "ineligible"):
        print(f"  level {k:<11}legacy {int(lvl_old.get(k, 0)):>7,}   new {int(lvl_new.get(k, 0)):>7,}")

    ho, hn = o["is_high_migration_rural"], c["is_high_migration_rural"]
    dropped, added = ho & ~hn, hn & ~ho
    print(f"\nhigh_migr_rural legacy {int(ho.sum()):>7,}   new {int(hn.sum()):>7,}   "
          f"dropped {int(dropped.sum())}   added {int(added.sum())}")
    if int(added.sum()):
        failures.append(f"is_high_migration_rural: {int(added.sum())} tracts newly True "
                        f"— the new column is NOT a subset of the old")
    if int(hn.sum()) >= int(ho.sum()):
        failures.append("is_high_migration_rural: new set is not strictly smaller")
    d = o[dropped]
    if len(d):
        print(f"  dropped: non-metro {int(d['is_non_metro'].sum())}/{len(d)}, "
              f"still eligible {int(d['nmtc_eligible'].sum())}/{len(d)}, "
              f"poverty>=20% {int((d['poverty_rate'] >= 0.20).sum())}/{len(d)}, "
              f"MFI range {d['ami_ratio'].min()*100:.1f}%-{d['ami_ratio'].max()*100:.1f}%")
    k = c[hn]
    print(f"  kept   : non-metro {int(k['is_non_metro'].sum())}/{len(k)}, "
          f"eligible {int(k['nmtc_eligible'].sum())}/{len(k)}, "
          f"MFI max {k['ami_ratio'].max()*100:.2f}%, MFI NA {int(k['ami_ratio'].isna().sum())}")

    if failures:
        print("\nGATE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nGATE PASSED: verdict unchanged for every tract; column N strictly narrowed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
