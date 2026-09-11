"""
NMTC eligibility checker — applies eligibility rules to census tract data.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from nmtcmapper.data.schema import (
    DISTRESS_LEVELS, CT_LEGACY_COUNTY_PREFIXES,
    DECIA_TERRITORY_STATE_FIPS, DECIA_TERRITORY_NAMES,
    DECIA_ISLAND_AREAS_FILE_TITLE,
)

# The "not covered" block, rendered once and shared by both status ladders so
# the wording cannot drift between check_address() and enrich_dataframe().
NOT_COVERED_DESCRIPTION = (
    "Not covered — outside this table's universe, NOT a lookup miss"
)


def _decia_territory_name(tract_id) -> Optional[str]:
    """The jurisdiction name when a GEOID is in a DECIA territory, else None.

    Keyed on the state FIPS prefix. Puerto Rico (72) deliberately returns None:
    PR IS in the loaded table's universe, so a PR miss is a real lookup miss.

    ONLY a well-formed 11-digit GEOID can carry a territory claim. Without the
    length guard, a leading-zero-stripped California id — "6037101110" or the
    int 6037101110, the shape Excel and CSV emit — slices to "60" and is told
    it is American Samoa: 8,707 tracts on the live table, every one in
    California. That input is a malformed id, and for a malformed id the true
    answer is the vague one, ``not-found`` (README, Known limitations). No
    normalization here: zfill would change answers for every caller who gets
    ``not-found`` today, and is 0.7.0 work with its own methodology.
    """
    if tract_id is None:
        return None
    s = str(tract_id)
    if len(s) != 11 or not s.isdigit():
        return None   # not a well-formed GEOID: no territory claim is possible
    fips = s[:2]
    if fips in DECIA_TERRITORY_STATE_FIPS:
        return DECIA_TERRITORY_NAMES[fips]
    return None


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
    - ``is_oz2_nomination_eligible`` and ``is_rural_area_qoz_eligible`` are
      ``Optional[bool]`` sourced from Treasury's OZ 2.0 data-transparency file.
      **THIS RESULT NOW CARRIES TWO FIELDS WHOSE NAMES BOTH START "OZ" AND WHOSE
      ``False`` MEAN OPPOSITE THINGS.** ``is_opportunity_zone`` is OZ 1.0 and can
      never return ``False`` at all; ``is_oz2_nomination_eligible`` is OZ 2.0 and
      its ``False`` is a real published fact about 60,197 tracts. They are
      different programs on different tract schemes: OZ 1.0 designations are
      2010-basis, OZ 2.0 eligibility is 2020-basis on the 2024 TIGER vintage.
      Neither field is a substitute for the other and no code should treat them
      as versions of one answer. Read ``opportunity_zone_status`` and
      ``oz2_nomination_status``.

      Nothing here is a DESIGNATION. No tract has been designated a 2027 QOZ and
      none can be yet: nominations close 2026-09-28 (2026-10-28 with the
      §1400Z-1(b)(2) extension) and the Secretary's consideration period runs to
      2026-12-28 at the latest. ``True`` means "eligible to be nominated", and a
      State may designate only 25% of its LICs (25 tracts where it has fewer than
      100), so a State's eligible tracts materially exceed what it may ever
      designate. ``True`` is not "will be an OZ".
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

    # ── OZ 2.0 nomination eligibility (0.6.0) ────────────────────────────────
    # A DIFFERENT PROGRAM FROM is_opportunity_zone, WITH THE OPPOSITE False.
    # Read oz2_nomination_status / rural_area_qoz_status, never truthiness.
    is_oz2_nomination_eligible: Optional[bool] = None
    is_rural_area_qoz_eligible: Optional[bool] = None
    # PROVENANCE, NOT A VERDICT. True when Treasury published eligible_lic = 0
    # for a tract whose poverty_rate AND mfi_ratio are both blank — i.e. a 0
    # produced with no measurable input. 1,080 live rows. It qualifies the False
    # above; it is not itself an eligibility answer. See oz2_nomination_status.
    oz2_inputs_missing: Optional[bool] = None

    @property
    def distress_description(self) -> str:
        """Human-readable expansion of the result — the SAME string summary()
        prints on its Description line.

        Selected from ``eligibility_status`` first: a ``not-covered-territory``
        result reads ``NOT_COVERED_DESCRIPTION`` rather than the "no match /
        tract absent" wording, because a coverage boundary is not a lookup miss.
        Selected here, not in summary(), so the two public surfaces cannot
        disagree on one object — 7d18d7f substituted the wording in summary()
        only and this property kept saying what the CHANGELOG said was removed.
        ``distress_level`` stays "unknown": it is a distress vocabulary and a
        coverage boundary is not a distress finding.
        """
        if self.eligibility_status == "not-covered-territory":
            return NOT_COVERED_DESCRIPTION
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
    def oz2_nomination_status(self) -> str:
        """OZ 2.0 nomination-eligibility status. READ THIS, NOT THE BOOLEAN.

        eligible-for-nomination / ineligible-on-treasury-inputs /
        ineligible-no-inputs-published / refused-connecticut-scheme /
        not-determined / no-tract

        Six values because ``is_oz2_nomination_eligible`` has three and two of
        them are not one fact each:

        * ``ineligible-on-treasury-inputs`` — Treasury scored the tract on the
          2020-2024 ACS / 2020 DECIA and published 0. A real published negative.
        * ``ineligible-no-inputs-published`` — Treasury published 0 for a tract
          whose poverty_rate AND mfi_ratio are BOTH blank. 1,080 live rows,
          1,047 of them reachable through this package's own tract universe. The
          value is still ``False``, because 0 is what Treasury published and this
          package does not overrule a federal determination — but it is a 0 with
          nothing behind it, and Treasury's own convention elsewhere in the file
          proves a missing input does not by itself defeat eligibility (1,068
          tracts with a blank mfi_ratio and poverty >= 20% were published 1).
          Callers who must not act on an unmeasured negative switch on THIS.
        * ``refused-connecticut-scheme`` — the GEOID is a Connecticut LEGACY
          county key (09001-09015), which is the scheme this package's NMTC table
          uses and NOT the scheme Treasury's file uses (09110-09190, COG/planning
          regions). The two are disjoint: zero shared GEOIDs. This is a REFUSAL,
          said out loud, not a lookup miss — 243 eligible CT tracts and 884 CT
          tracts overall are unanswerable through the NMTC key, and a silent
          ``None`` for an entire state is the misdescription this package exists
          to stop. A CT answer requires a 09110-09190 key.
        """
        if self.tract_id is None:
            return "no-tract"
        if str(self.tract_id)[:5] in CT_LEGACY_COUNTY_PREFIXES:
            return "refused-connecticut-scheme"
        if self.is_oz2_nomination_eligible is None:
            return "not-determined"
        if self.is_oz2_nomination_eligible:
            return "eligible-for-nomination"
        if self.oz2_inputs_missing:
            return "ineligible-no-inputs-published"
        return "ineligible-on-treasury-inputs"

    @property
    def rural_area_qoz_status(self) -> str:
        """Rural-area QOZ status. READ THIS, NOT THE BOOLEAN.

        rural-eligible / not-rural-on-treasury-determination /
        not-determined-not-an-eligible-lic / refused-connecticut-scheme /
        not-determined / no-tract

        ``not-determined-not-an-eligible-lic`` is its own value because it is the
        overwhelmingly common ``None`` (60,197 rows) and it is NOT ignorance:
        Treasury populates rural_status for the whole 85,529-row universe, but
        its rural methodology determines rural status over ELIGIBLE tracts only.
        20,377 ineligible tracts carry rural_status = 1 and this package reports
        none of them, because a populated column is not a published determination.
        """
        if self.tract_id is None:
            return "no-tract"
        if str(self.tract_id)[:5] in CT_LEGACY_COUNTY_PREFIXES:
            return "refused-connecticut-scheme"
        if self.is_rural_area_qoz_eligible is True:
            return "rural-eligible"
        if self.is_rural_area_qoz_eligible is False:
            return "not-rural-on-treasury-determination"
        if self.is_oz2_nomination_eligible is False:
            return "not-determined-not-an-eligible-lic"
        return "not-determined"

    @property
    def eligibility_status(self) -> str:
        """Five-way status distinguishing the indeterminate cases from verdicts.

        verified-eligible / verified-ineligible / not-found /
        not-covered-territory / geocode-failed.

        ``not-covered-territory`` (0.6.0) separates a STRUCTURAL non-coverage
        from a lookup miss: the four DECIA territories are outside the loaded
        2016-2020 ACS table's universe entirely, so "not found in the table" is
        a true statement that misdescribes the situation — there is no retry
        that helps, the remedy is a different file. See
        ``DECIA_TERRITORY_STATE_FIPS``. Both remain INDETERMINATE:
        ``nmtc_eligible`` is None in either case, never False.
        """
        if not self.geocode_success:
            return "geocode-failed"
        if not self.tract_found:
            # Order matters: after geocode-failed (a territory tract that never
            # geocoded must report the geocode failure), before the generic miss.
            if _decia_territory_name(self.tract_id):
                return "not-covered-territory"
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
        # The Description line is READ from distress_description, never
        # re-decided here — that property owns the status-first selection.
        status = self.eligibility_status
        description = self.distress_description
        if status == "not-covered-territory":
            territory = _decia_territory_name(self.tract_id)
            elig = (
                # Wrapped so the FULL FILE TITLE survives on one line — a user
                # has to be able to copy it out and search for it; that title
                # is the entire remedy this block exists to deliver. It is read
                # from the schema constant, never retyped here.
                f"🚫 NOT COVERED — {territory} is outside the 2016-2020 ACS\n"
                "                    NMTC LIC table this package loads (50 states + DC + PR).\n"
                "                    Territory LIC status is published separately, in the CDFI Fund's\n"
                f"                    \"{DECIA_ISLAND_AREAS_FILE_TITLE}\"\n"
                "                    file. This package does not load it."
            )
        elif self.nmtc_eligible is None:
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
        print(f"  Description:      {description}")
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
        # OZ 2.0 — switched on the status string for the same reason the OZ 1.0
        # line is: a ternary on the value would print "No" for every indeterminate
        # and refused tract. The Connecticut refusal is printed IN FULL rather
        # than collapsed into "unknown"; a silent None for an entire state is the
        # failure this block exists to prevent.
        oz2 = self.oz2_nomination_status
        oz2_line = {
            "eligible-for-nomination":
                "✅ YES — eligible to be NOMINATED as a 2027 QOZ (not designated;\n"
                "                    no tract is designated yet)",
            "ineligible-on-treasury-inputs":
                "❌ NO — not an eligible LIC on the 2020-2024 ACS / 2020 DECIA\n"
                "                    inputs Treasury used",
            "ineligible-no-inputs-published":
                "❌ NO (published) — but Treasury had NO poverty and NO income\n"
                "                    data for this tract; the 0 has nothing behind it",
            "refused-connecticut-scheme":
                "🚫 REFUSED — Connecticut legacy county key (09001-09015).\n"
                "                    Treasury keys CT on COG/planning regions\n"
                "                    (09110-09190); the two share ZERO GEOIDs. Supply\n"
                "                    a 09110-09190 key for a Connecticut answer.",
            "not-determined":
                "❓ NOT DETERMINED — tract absent from Treasury's 85,529-row universe",
            "no-tract":
                "❓ UNKNOWN — no census tract resolved",
        }[oz2]
        print(f"  OZ 2.0 Eligible:  {oz2_line}")
        rural = self.rural_area_qoz_status
        rural_line = {
            "rural-eligible":
                "✅ YES — Treasury determined this eligible tract is comprised\n"
                "                    entirely of a rural area",
            "not-rural-on-treasury-determination":
                "❌ NO — eligible, but not comprised entirely of a rural area",
            "not-determined-not-an-eligible-lic":
                "❓ NOT DETERMINED — Treasury determines rural status only for\n"
                "                    ELIGIBLE tracts, and this tract is not one",
            "refused-connecticut-scheme":
                "🚫 REFUSED — Connecticut legacy county key (see above)",
            "not-determined":
                "❓ NOT DETERMINED — tract absent from Treasury's universe",
            "no-tract":
                "❓ UNKNOWN — no census tract resolved",
        }[rural]
        print(f"  Rural-Area QOZ:   {rural_line}")
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
    # Additive column (0.4.0; a fifth value added in 0.6.0) distinguishing
    # the outcomes:
    # verified-eligible / verified-ineligible / not-found /
    # not-covered-territory / geocode-failed.
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
            # SECOND, INDEPENDENT status ladder — it must stay in lockstep with
            # EligibilityResult.eligibility_status. Fixing only the property
            # would make check_address() say not-covered-territory while this
            # path said not-found for the same GEOID.
            df.at[idx, "eligibility_status"] = (
                "not-covered-territory" if _decia_territory_name(tract_id)
                else "not-found"
            )
        elif result["nmtc_eligible"]:
            df.at[idx, "eligibility_status"] = "verified-eligible"
        else:
            df.at[idx, "eligibility_status"] = "verified-ineligible"

    return df
