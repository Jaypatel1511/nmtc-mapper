"""
NMTC eligibility checker — applies eligibility rules to census tract data.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from nmtcmapper.data.schema import DISTRESS_LEVELS


def _tri(value: Optional[bool]) -> str:
    """Render a tri-state boolean for summary() — three branches, never a ternary.

    `None` is falsy, so any `'Yes' if x else 'No'` on a tri-state field prints a
    fabricated `No` for a tract the package never read. The qualifier is inline.
    """
    if value is None:
        return "❓ UNKNOWN — tract not read"
    if value:
        return "Yes"
    return "No"


# What a demographic rate renders as when the Fund published no value for a tract
# it DID publish a determination for. Distinct wording from _tri()'s "tract not
# read", because these are two different states and collapsing them into one word
# is what made this defect invisible for four releases.
_NOT_AVAILABLE = "not available — the CDFI Fund published no value for this tract"


def _pct(value: Optional[float]) -> str:
    """Render an Optional[float] rate as a percentage — THREE outcomes (0.5.0).

    TWO KINDS OF MISSING, TWO DIFFERENT WORDS:

    * ``None``  -> "tract not read". The indeterminate branches; no row exists.
    * ``NaN``   -> "not available". A FOUND tract whose demographic cell the Fund
      published as ``NA``. The Fund still published a YES/NO determination for it,
      so the verdict is real and only the metric is missing — 1,583 tracts for
      poverty and 2,358 for AMI on the live file.
    * a number  -> the percentage.

    THE GUARD THIS REPLACES WAS WRITTEN FOR THE WRONG SENTINEL. It read
    ``if self.poverty_rate is not None:`` — correct against the ``None`` the
    loader emits, and a no-op against what actually arrives, because
    ``pd.DataFrame(records)`` coerces ``None`` to ``NaN`` in a float column and
    ``NaN is not None`` is ``True``. Those 1,583 + 2,358 tracts rendered
    ``nan%``. This is the third instance of the pattern in this portfolio
    (hmda-analyzer 0.6.0: a ``!= "NA"`` filter that was a no-op because the
    loader had already produced ``NaN``), so the test here is ``pd.isna`` rather
    than a second hand-written sentinel check: it catches ``None``, ``np.nan``,
    ``pd.NA`` and ``pd.NaT`` alike, including whichever null the next pandas
    version introduces. ``None`` is still tested FIRST, because ``pd.isna(None)``
    is also True and the two states must not collapse back into one.

    Every line is printed UNCONDITIONALLY. The old guard's else-branch was to
    omit the line entirely, which is a third rendering of "missing" that a reader
    cannot distinguish from "I forgot to look".
    """
    if value is None:
        return "❓ UNKNOWN — tract not read"
    if pd.isna(value):
        return _NOT_AVAILABLE
    return f"{value * 100:.1f}%"


@dataclass
class EligibilityResult:
    """Result of a single address NMTC eligibility check.

    ``nmtc_eligible`` is TRI-STATE (0.4.0): True (verified eligible), False
    (verified ineligible — the table explicitly says NO), or None
    (INDETERMINATE — geocode no-match, or the tract is absent from the ~85k
    universe). None must never be read as a falsy "ineligible": see
    ``eligibility_status`` and ``summary()``.

    0.5.0 EXTENDS THAT CONTRACT TO EVERY BOOLEAN THAT CAN BE UNOBTAINABLE.
    0.4.0 made the verdict tri-state and left its neighbours fabricating inside
    the very branches written to protect it: the tract-absent branch of
    ``check_tract()`` and the geocode-no-match branch of ``check_address()`` set
    six booleans to a confident ``False`` about a tract no row was ever read for.

    - ``is_non_metro``, ``is_high_migration_rural``, ``severe_distress`` and
      ``deep_distress`` are ``Optional[bool]``, and are ``None`` ONLY on those two
      indeterminate branches. FOR A FOUND TRACT THEIR ``False`` IS UNCHANGED and
      is fully supportable: it is the Fund's published ``NO``, verified strict
      YES/NO across all 85,395 rows with zero blanks — including the 2,750 rows
      with null demographics, for which the Fund still published a determination.
      The rule is per-observation, not per-field: tri-state where a positive is
      obtainable, and on those branches nothing at all was read.
    - ``is_opportunity_zone`` is ``Optional[bool]`` on EVERY path: ``True`` when
      the GEOID is on the Dec-2018 designation list, ``None`` otherwise. ``False``
      is never returnable. The designations are 2010-tract-based and this table
      and geocoder are 2020-basis, so a non-match and a genuine non-designation
      are the same observation. Read ``opportunity_zone_status`` rather than the
      truthiness of the field.
    - ``poverty_rate``, ``ami_ratio`` and ``unemployment_rate`` HAVE TWO KINDS OF
      MISSING, and the distinction is part of the contract. ``None`` means no row
      was read (the two indeterminate branches). ``NaN`` means a FOUND tract whose
      metric the Fund published as ``NA`` — 1,583 rows for poverty and 2,358 for
      AMI, all of which still carry a real published YES/NO verdict. So
      ``r.poverty_rate is None`` is NOT a missing-value test on this field; use
      ``pd.isna(r.poverty_rate)`` for "no number available either way", and
      ``eligibility_status`` to tell which kind. ``summary()`` prints two
      different words for the two states (0.5.0).
    - ``is_nmtc_native_area`` IS REMOVED. It was never obtainable — the CDFI Fund
      publishes no tract-keyed NMTC native-area resource, and AIANNH entities
      carry four-digit GEOIDs with no state or county component, so they cannot
      nest into SSCCCTTTTTT at all. A field that can only ever say "I don't know"
      invites a consumer to read the absence of True as meaningful; dropping it
      fails loud (AttributeError / TypeError) where a tri-state would fail silent.
    """
    address: str
    tract_id: Optional[str]
    nmtc_eligible: Optional[bool]
    distress_level: str
    poverty_rate: Optional[float]
    ami_ratio: Optional[float]
    unemployment_rate: Optional[float]
    # Tri-state (0.5.0): None ONLY on the two indeterminate branches. A found
    # tract's False is the Fund's published NO and is unchanged.
    is_non_metro: Optional[bool]
    is_high_migration_rural: Optional[bool]
    severe_distress: Optional[bool]
    deep_distress: Optional[bool]
    # Means "no unresolved address stands between this result and its tract" —
    # NOT "geocoding succeeded". check_tract() sets it True with no geocoding
    # performed, because the caller supplied the GEOID. Stays a plain bool.
    geocode_success: bool
    # Tri-state (0.5.0), True or None, NEVER False. See the class docstring and
    # opportunity_zone_status. Keyed on designation-set membership, NOT on
    # tract_found: a retired 2010 GEOID that is designated correctly returns True
    # alongside tract_found=False, which is the one place the OZ answer is more
    # complete than the eligibility answer.
    is_opportunity_zone: Optional[bool] = None
    tract_found: bool = True

    @property
    def distress_description(self) -> str:
        return DISTRESS_LEVELS.get(self.distress_level, "Unknown")

    @property
    def opportunity_zone_status(self) -> str:
        """Three-way OZ status, parallel to ``eligibility_status`` (0.5.0).

        designated / not-confirmed / no-tract.

        Exists because ``bool -> Optional[bool]`` breaks silently: ``None`` is
        falsy, so ``if r.is_opportunity_zone:`` keeps running and starts meaning
        something else. Switch on this instead — ``summary()`` does.

        Three values, not four. The reasons behind ``not-confirmed`` — genuinely
        not designated, a 2010->2020 vintage miss, or an Island Area outside this
        table — are exactly what the package CANNOT distinguish, so enumerating
        them as separate statuses would re-introduce the fabrication in string
        form.
        """
        if self.is_opportunity_zone:
            return "designated"
        if self.tract_id is None:
            # No GEOID in hand; there is nothing to test membership against.
            return "no-tract"
        return "not-confirmed"

    @property
    def eligibility_status(self) -> str:
        """Four-way status distinguishing the indeterminate cases from verdicts.

        verified-eligible / verified-ineligible / not-found / geocode-failed.
        """
        if not self.geocode_success:
            return "geocode-failed"
        if not self.tract_found:
            return "not-found"
        # Guard None FIRST, exactly as summary() does: an indeterminate verdict
        # must never fall through the falsy branch and surface as a fabricated
        # "verified-ineligible" (C2).
        if self.nmtc_eligible is None:
            return "not-found"
        return "verified-eligible" if self.nmtc_eligible else "verified-ineligible"

    def summary(self) -> None:
        print(f"\nNMTC Eligibility Result")
        print(f"{'='*50}")
        print(f"  Address:          {self.address}")
        print(f"  Census Tract:     {self.tract_id or 'Not found'}")
        # Tri-state: an indeterminate result must NOT print "❌ NO". The reason it
        # is unknown is qualified inline on the same line (not in a footer).
        if self.nmtc_eligible is None:
            if not self.geocode_success:
                elig = "❓ UNKNOWN — address could not be geocoded (indeterminate, NOT ineligible)"
            else:
                elig = "❓ UNKNOWN — tract not in eligibility table (indeterminate, NOT ineligible)"
        elif self.nmtc_eligible:
            elig = "✅ YES"
        else:
            elig = "❌ NO"
        print(f"  NMTC Eligible:    {elig}")
        print(f"  Distress Level:   {self.distress_level.upper()}")
        print(f"  Description:      {self.distress_description}")
        # Three-branch switch via _pct(), printed unconditionally — see _pct's
        # docstring. `is not None` was the wrong sentinel: the loader's None
        # becomes NaN inside the DataFrame, NaN is not None, and 1,583 poverty /
        # 2,358 AMI found tracts rendered `nan%`.
        print(f"\n  Poverty Rate:     {_pct(self.poverty_rate)}")
        print(f"  AMI Ratio:        {_pct(self.ami_ratio)}")
        print(f"  Unemployment:     {_pct(self.unemployment_rate)}")
        # EVERY line below is a three-branch switch, NEVER a ternary on the value.
        # `None` is falsy, so `'Yes' if x else 'No'` would keep printing "No"
        # after the type was fixed — the human-readable block is the thing a user
        # pastes into a memo, so the fabricated negative has to be killed here
        # explicitly, not just in the type. Qualifiers are INLINE on the same
        # line, never a footer: a footer is what gets dropped when one line is
        # copied out.
        print(f"  Non-Metro:        {_tri(self.is_non_metro)}")
        # Switched on opportunity_zone_status, not on truthiness — which is what
        # structurally prevents the ternary trap from coming back.
        oz = self.opportunity_zone_status
        if oz == "designated":
            oz_line = ("✅ YES — GEOID is on the Dec-2018 designation list, which is\n"
                       "                    2010-tract-based (a claim about the list, "
                       "not about the parcel)")
        elif oz == "not-confirmed":
            oz_line = ("❓ NOT CONFIRMED — not on the 2018 designation list, which is\n"
                       "                    2010-tract-based (indeterminate, NOT "
                       "\"not an Opportunity Zone\")")
        else:
            oz_line = "❓ UNKNOWN — no census tract resolved"
        print(f"  Opportunity Zone: {oz_line}")
        print(f"  High Migration:   {_tri(self.is_high_migration_rural)}")
        print()


def check_tract(
    tract_id: str,
    eligibility_table: pd.DataFrame,
) -> dict:
    """
    Check NMTC eligibility for a known census tract ID.

    Args:
        tract_id:          11-digit census tract GEOID
        eligibility_table: DataFrame indexed by tract_id

    Returns:
        Dict with eligibility fields
    """
    if tract_id not in eligibility_table.index:
        # LOOKUP MISS (Fix 3). The table is the full ~85k-tract universe with an
        # explicit YES/NO flag, so a tract that is ABSENT is not "ineligible" —
        # it is a bad/unknown tract id or a vintage mismatch. Return an
        # INDETERMINATE verdict (nmtc_eligible None, distress "unknown", metrics
        # None) and an explicit tract_found=False so a caller can tell "table
        # says NO" from "tract absent" without having to notice metrics are None.
        #
        # 0.5.0: the four supporting booleans are None here too. Through 0.4.3
        # this branch — written specifically to stop the package fabricating a
        # verdict — set every one of them to a confident False about a tract no
        # row was read for, so `df[~df.is_high_migration_rural]` and
        # `result.severe_distress` returned confident wrong answers while
        # `eligibility_status` (the field designed to make this impossible to
        # miss) sat on a different attribute.
        return {
            "nmtc_eligible": None,
            "distress_level": "unknown",
            "poverty_rate": None,
            "ami_ratio": None,
            "unemployment_rate": None,
            "is_non_metro": None,
            "is_high_migration_rural": None,
            "severe_distress": None,
            "deep_distress": None,
            "tract_found": False,
        }

    row = eligibility_table.loc[tract_id]
    return {
        "nmtc_eligible":         bool(row.get("nmtc_eligible", False)),
        "distress_level":        str(row.get("distress_level", "ineligible")),
        "poverty_rate":          row.get("poverty_rate"),
        "ami_ratio":             row.get("ami_ratio"),
        "unemployment_rate":     row.get("unemployment_rate"),
        "is_non_metro":          bool(row.get("is_non_metro", False)),
        "is_high_migration_rural": bool(row.get("is_high_migration_rural", False)),
        "severe_distress":       bool(row.get("severe_distress", False)),
        "deep_distress":         bool(row.get("deep_distress", False)),
        "tract_found":           True,
    }


def enrich_dataframe(
    df: pd.DataFrame,
    eligibility_table: pd.DataFrame,
    tract_col: str = "tract_id",
) -> pd.DataFrame:
    """
    Add NMTC eligibility columns to a DataFrame that already has tract IDs.

    Args:
        df:                DataFrame with tract_id column
        eligibility_table: Full eligibility lookup table
        tract_col:         Name of the tract ID column

    Returns:
        DataFrame with added eligibility columns
    """
    df = df.copy()

    # 0.5.0 dropped is_nmtc_native_area, so this writes NINE eligibility columns
    # plus eligibility_status. The frame is object-dtype, so the four tri-state
    # columns store None correctly — but note that `~df["severe_distress"]` now
    # raises TypeError on a frame containing indeterminate rows. Filter with
    # `df["severe_distress"] != True`.
    eligibility_cols = [
        "nmtc_eligible", "distress_level", "poverty_rate",
        "ami_ratio", "unemployment_rate", "is_non_metro",
        "is_high_migration_rural", "severe_distress", "deep_distress",
    ]

    for col in eligibility_cols:
        df[col] = None
    # Additive column (0.4.0) distinguishing the four outcomes:
    # verified-eligible / verified-ineligible / not-found / geocode-failed.
    df["eligibility_status"] = None

    for idx, row in df.iterrows():
        tract_id = row.get(tract_col)
        if pd.isna(tract_id):
            # No tract resolved (geocoding failed / no tract supplied) —
            # INDETERMINATE, never a fabricated False/"ineligible".
            df.at[idx, "nmtc_eligible"] = None
            df.at[idx, "distress_level"] = "unknown"
            df.at[idx, "eligibility_status"] = "geocode-failed"
            continue

        result = check_tract(str(tract_id), eligibility_table)
        found = result.pop("tract_found")
        for col, val in result.items():
            df.at[idx, col] = val
        if not found:
            df.at[idx, "eligibility_status"] = "not-found"
        elif result["nmtc_eligible"]:
            df.at[idx, "eligibility_status"] = "verified-eligible"
        else:
            df.at[idx, "eligibility_status"] = "verified-ineligible"

    return df
