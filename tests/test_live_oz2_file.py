"""@live gates — download and parse the REAL Treasury OZ 2.0 file (0.6.0).

Network-bound and deselected in CI (`-m "not live"`). Run locally with:

    pytest tests/test_live_oz2_file.py -m live -v

Not skip-marked: these run whenever `live` is selected, and never otherwise.

WHY THE FIGURE GATE LIVES HERE. Every OZ 2.0 count this release publishes is
asserted against the file at test time, not typed. The offline half of that gate
(`test_no_oz2_figure_is_hand_typed`) checks that every figure in the README and
the CHANGELOG appears in ONE manifest; this module checks that manifest against
Treasury's bytes. Neither half alone is worth anything — prose agreeing with a
hand-written manifest certifies nothing, and a manifest agreeing with reality
does not stop the prose drifting from it. The seam is stated rather than hidden.
"""
import hashlib

import pytest

from nmtcmapper.data.loader import load_oz2_table, download_oz2_file
from nmtcmapper.data.schema import (
    OZ2_SHA256, OZ2_TRACT_BINDING, TRACT_SCHEME_COG_PLANNING_REGION,
    CT_COG_COUNTY_PREFIXES,
)
from tests.test_oz2 import (
    SPECIMENS, REAL_INELIGIBLE_RURAL, REAL_INELIGIBLE_NOINPUT,
    REAL_CT_LEGACY_ABSENT, OZ2_PUBLISHED_FIGURES,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_oz2():
    return load_oz2_table()


def test_the_pinned_digest_still_matches(): 
    """Treasury is EXPECTED to revise this file: its Appendix sheet is named
    `..._cor` and its OOXML dcterms:created (2026-04-06) is two weeks after the
    date in its own filename (03232026). This is not a load-time gate — a hard
    digest check would turn every future correction into a total outage — it is
    the gate that REPORTS a re-publish so the counts below can be re-derived
    deliberately rather than drifting."""
    path = download_oz2_file()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == OZ2_SHA256, (
        f"Treasury has re-published the OZ 2.0 file.\n"
        f"  pinned: {OZ2_SHA256}\n  live  : {digest}\n"
        f"Re-derive every OZ 2.0 figure before shipping anything that quotes one."
    )


def test_the_universe_and_both_flag_partitions(live_oz2):
    f = OZ2_PUBLISHED_FIGURES
    assert len(live_oz2) == f["oz2_universe"]
    elig = live_oz2["oz2_nomination_eligible"]
    assert int(elig.sum()) == f["oz2_eligible"]
    assert int((~elig).sum()) == f["oz2_ineligible"]
    rural = live_oz2["oz2_rural_area_qoz"]
    assert int((rural == True).sum()) == f["oz2_rural_eligible"]      # noqa: E712
    assert int((rural == False).sum()) == f["oz2_nonrural_eligible"]  # noqa: E712
    assert int(rural.isna().sum()) == f["oz2_ineligible"]


def test_the_rural_restriction_holds_across_the_whole_live_universe(live_oz2):
    """Not one specimen — every row. A rural answer exists if and only if the
    tract is an eligible LIC."""
    elig = live_oz2["oz2_nomination_eligible"]
    has_rural = live_oz2["oz2_rural_area_qoz"].notna()
    assert (has_rural == elig).all()


def test_no_ineligible_tract_leaks_a_rural_answer(live_oz2):
    """Treasury flags 20,377 INELIGIBLE tracts rural. This package reports none
    of them: its rural methodology determines rural status over eligible tracts
    only, and a populated column is not a published determination."""
    ineligible = live_oz2[~live_oz2["oz2_nomination_eligible"]]
    assert len(ineligible) == OZ2_PUBLISHED_FIGURES["oz2_ineligible"]
    assert ineligible["oz2_rural_area_qoz"].isna().all()


def test_the_no_inputs_population_is_what_the_release_documents(live_oz2):
    """The finding this release adds. Treasury published eligible_lic = 0 for
    tracts with NO poverty_rate and NO mfi_ratio at all."""
    f = OZ2_PUBLISHED_FIGURES
    miss = live_oz2["oz2_inputs_missing"]
    assert int(miss.sum()) == f["oz2_no_inputs"]
    # Every one of them is a published 0 — none is an eligible tract.
    assert int((miss & live_oz2["oz2_nomination_eligible"]).sum()) == 0


def test_the_no_inputs_sub_populations_are_derived_not_typed(live_oz2):
    """The three figures the 0.6.0 CHANGELOG quotes about the no-inputs finding.
    Derived here from Treasury's own cells and the CDFI Fund's own universe —
    the loader exposes only the combined flag, so the sub-populations are read
    back off the workbook rather than inferred from it."""
    import openpyxl
    from nmtcmapper.data.loader import download_oz2_file, load_eligibility_table
    from nmtcmapper.data.schema import OZ2_SHEET, OZ2_EXPECTED_HEADERS
    f = OZ2_PUBLISHED_FIGURES

    wb = openpyxl.load_workbook(download_oz2_file(), read_only=True, data_only=True)
    rows = wb[OZ2_SHEET].iter_rows(values_only=True)
    next(rows)
    I = {n: i for i, n in enumerate(OZ2_EXPECTED_HEADERS)}

    def blank(v):
        return v is None or (isinstance(v, str) and not v.strip())

    no_input, missing_mfi_eligible = [], 0
    for r in rows:
        if r[I["census_tract_number"]] is None:
            continue
        g = str(r[I["census_tract_number"]]).strip().zfill(11)
        if blank(r[I["mfi_ratio"]]) and r[I["eligible_lic"]] == 1:
            missing_mfi_eligible += 1
        if blank(r[I["poverty_rate"]]) and blank(r[I["mfi_ratio"]]):
            no_input.append(g)
    wb.close()

    assert len(no_input) == f["oz2_no_inputs"]
    # Treasury's convention: a MISSING mfi_ratio does not defeat eligibility.
    # This is the evidence that the 1,080 zeroes are zeroes only because nothing
    # at all was measurable, and it is why the status string separates them.
    assert missing_mfi_eligible == f["oz2_missing_mfi_but_eligible"]
    assert missing_mfi_eligible > 0

    nmtc = set(load_eligibility_table().index)
    assert len([g for g in no_input if g in nmtc]) == f["oz2_no_inputs_reachable"]
    ordinary = [g for g in no_input if not (g[5] == "9" and g[6] in "89")]
    assert len(ordinary) == f["oz2_no_inputs_ordinary_codes"]


def test_the_connecticut_figures_are_derived_not_typed(live_oz2):
    from nmtcmapper.data.loader import load_eligibility_table
    f = OZ2_PUBLISHED_FIGURES
    ct = [g for g in live_oz2.index if g.startswith("09")]
    assert len(ct) == f["oz2_ct_tracts"]
    assert int(live_oz2.loc[ct, "oz2_nomination_eligible"].sum()) == f["oz2_ct_eligible"]
    nmtc = load_eligibility_table()
    assert len([g for g in nmtc.index if g.startswith("09")]) == f["nmtc_ct_tracts"]


def test_the_rural_but_ineligible_population_is_derived_not_typed():
    """20,377 — the tracts Treasury flags rural that this package reports as
    None. Read from the workbook, since the loader deliberately discards the
    unrestricted flag rather than carrying it where a consumer could reach it."""
    import openpyxl
    from nmtcmapper.data.loader import download_oz2_file
    from nmtcmapper.data.schema import OZ2_SHEET, OZ2_EXPECTED_HEADERS
    wb = openpyxl.load_workbook(download_oz2_file(), read_only=True, data_only=True)
    rows = wb[OZ2_SHEET].iter_rows(values_only=True)
    next(rows)
    I = {n: i for i, n in enumerate(OZ2_EXPECTED_HEADERS)}
    n = sum(1 for r in rows
            if r[I["census_tract_number"]] is not None
            and r[I["rural_status"]] == 1 and r[I["eligible_lic"]] == 0)
    wb.close()
    assert n == OZ2_PUBLISHED_FIGURES["oz2_rural_but_ineligible"]


def test_every_offline_specimen_still_matches_treasurys_file(live_oz2):
    """The offline gates run on real values extracted from this file. If Treasury
    revises a specimen row, the offline suite would silently keep asserting the
    old value — this is the only thing that catches it."""
    for geoid, lic, rural in SPECIMENS:
        assert geoid in live_oz2.index, f"specimen {geoid} has left the file"
        row = live_oz2.loc[geoid]
        assert bool(row["oz2_nomination_eligible"]) is bool(lic), geoid
        want = (bool(rural) if lic else None)
        assert row["oz2_rural_area_qoz"] is want, geoid
    assert live_oz2.loc[REAL_INELIGIBLE_NOINPUT[0], "oz2_inputs_missing"]
    assert not live_oz2.loc[REAL_INELIGIBLE_RURAL[0], "oz2_inputs_missing"]


def test_connecticut_is_keyed_on_the_cog_scheme_and_the_legacy_key_is_absent(live_oz2):
    """The refusal's factual basis, on the live file: Treasury keys CT on
    COG/planning regions, and the legacy key this package's NMTC table uses is
    genuinely absent — the None is correct, not a lookup bug."""
    ct = [g for g in live_oz2.index if g.startswith("09")]
    assert {g[:5] for g in ct} == CT_COG_COUNTY_PREFIXES
    assert REAL_CT_LEGACY_ABSENT not in live_oz2.index
    assert OZ2_TRACT_BINDING.validate_table_scheme(
        live_oz2.index) == TRACT_SCHEME_COG_PLANNING_REGION


def test_the_live_scheme_is_disjoint_from_the_nmtc_tables_in_connecticut(live_oz2):
    """The measurement the whole two-binding design rests on, re-run rather than
    inherited: zero shared Connecticut GEOIDs across the two live tables."""
    from nmtcmapper.data.loader import load_eligibility_table
    nmtc = load_eligibility_table()
    ct_oz2 = {g for g in live_oz2.index if g.startswith("09")}
    ct_nmtc = {g for g in nmtc.index if g.startswith("09")}
    assert len(ct_oz2 & ct_nmtc) == 0
    # ...and identical at the six-digit tract-code level: a pure relabelling.
    assert {g[5:] for g in ct_oz2} == {g[5:] for g in ct_nmtc}
