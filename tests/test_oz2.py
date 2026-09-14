"""OZ 2.0 gates (0.6.0) — answer spaces, the rural restriction, the GEOID-scheme
discriminator, and the Connecticut/territory refusals.

Every gate here was demonstrated RED before it was accepted; the mutation that
reddens each one is named in its docstring. A gate never seen to fail is not
evidence, it is decoration.

REAL ROWS, NOT ROWS WRITTEN TO SUIT. The specimens below were extracted from
Treasury's own workbook (sheet `oz2_for_data_transparency`, SHA-256
9d41e658...d57e37dc0) by reading the raw cells, not the loader's interpretation
of them — the loader is the thing under test. `tests/test_live_oz2_file.py`
re-asserts every specimen against the live file, so a Treasury re-publish that
changed one of these rows is REPORTED rather than silently baked in here.
"""
import re
import pandas as pd
import pytest

from nmtcmapper.data.loader import load_oz2_table, _sample_oz2_table
from nmtcmapper.data.schema import (
    OZ2_TRACT_BINDING, OZ2TractBinding, derive_tract_scheme,
    TRACT_SCHEME_LEGACY_COUNTY, TRACT_SCHEME_COG_PLANNING_REGION,
    CT_LEGACY_COUNTY_PREFIXES, CT_COG_COUNTY_PREFIXES,
)
from nmtcmapper.exceptions import OZ2SchemaError
from nmtcmapper.mapper import NMTCMapper, _oz2_flags

# ── Real specimens, extracted from Treasury's workbook ───────────────────────
#   python - <<'PY'
#   import openpyxl
#   wb = openpyxl.load_workbook(CACHE/"OZ2_Eligible_LIC_Tracts_Treasury.xlsx",
#                               read_only=True, data_only=True)
#   sh = wb["oz2_for_data_transparency"] ...
#   PY
# (geoid, eligible_lic, rural_status)
REAL_ELIGIBLE_RURAL     = ("01001020700", 1, 1)
REAL_ELIGIBLE_NONRURAL  = ("01045021400", 1, 0)
# THE GATE-2 SPECIMEN: ineligible, yet Treasury's rural_status column says 1.
REAL_INELIGIBLE_RURAL   = ("01001020100", 0, 1)
# Ineligible with NO measurable input — poverty_rate and mfi_ratio both blank.
REAL_INELIGIBLE_NOINPUT = ("01003990000", 0, 0)
REAL_CT_COG_ELIGIBLE    = ("09110415300", 1, 0)
REAL_GUAM               = ("66010950100", 1, 1)
# Absent from Treasury's universe by construction: a Connecticut LEGACY key.
REAL_CT_LEGACY_ABSENT   = "09001020100"


SPECIMENS = [REAL_ELIGIBLE_RURAL, REAL_ELIGIBLE_NONRURAL, REAL_INELIGIBLE_RURAL,
             REAL_INELIGIBLE_NOINPUT, REAL_CT_COG_ELIGIBLE, REAL_GUAM]
# Only this specimen has both inputs blank; the others carry real numbers.
NO_INPUT_GEOIDS = {REAL_INELIGIBLE_NOINPUT[0]}


def _write_oz2_workbook(path, rows):
    """Write a workbook in Treasury's exact layout, then let THE REAL LOADER read
    it. Nothing in this module reimplements the loader's rules — a fixture that
    rebuilt the rural restriction by hand would test itself, and mutating the
    loader would leave every gate green. That is the vacuity class these gates
    exist to close, so it must not appear in the gates."""
    import openpyxl
    from nmtcmapper.data.schema import OZ2_EXPECTED_HEADERS, OZ2_SHEET
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = OZ2_SHEET
    ws.append(list(OZ2_EXPECTED_HEADERS))
    for geoid, lic, rural in rows:
        blank = geoid in NO_INPUT_GEOIDS
        ws.append([geoid, "S", "C", "",
                   None if blank else 25.0,           # poverty_rate
                   None if blank else 40000,          # mfi
                   50000, 50000, 50000,
                   None if blank else 0.8,            # mfi_ratio
                   lic, rural])
    # Filler to clear OZ2_MIN_ROWS. Keyed outside every specimen and outside
    # Connecticut so it can neither shadow a specimen nor affect scheme derivation.
    for i in range(1200):
        ws.append(["55025%06d" % i, "S", "C", "", 5.0, 90000, 50000, 50000,
                   50000, 1.8, 0, 0])
    wb.save(path)
    return path


@pytest.fixture(scope="module")
def real_rows_table(tmp_path_factory):
    """Treasury's real specimen values, through the real loader."""
    from nmtcmapper.data import loader as L
    p = _write_oz2_workbook(tmp_path_factory.mktemp("oz2") / "oz2.xlsx", SPECIMENS)
    orig = L.download_oz2_file
    L.download_oz2_file = lambda force=False: p
    try:
        return L.load_oz2_table()
    finally:
        L.download_oz2_file = orig


# ══════════════════════════════════════════════════════════════════════════════
# GATE 1 — answer spaces. Every value of both flags, and EACH None cause
# separately. The two None causes are different facts and a gate that merged
# them would pass while the package told a user "unknown" for a whole state.
# ══════════════════════════════════════════════════════════════════════════════

def test_g1_nomination_true(real_rows_table):
    """Mutation: make _oz2_flags return None for a found eligible row -> red."""
    f = _oz2_flags(REAL_ELIGIBLE_RURAL[0], real_rows_table)
    assert f["is_oz2_nomination_eligible"] is True


def test_g1_nomination_false_is_a_real_returnable_fact(real_rows_table):
    """The whole reason S5 is the source rather than the Appendix: a full
    universe with an explicit 0 makes a NO a fact.

    Mutation: return None instead of False on the eligible_lic == 0 branch -> red.
    """
    f = _oz2_flags(REAL_INELIGIBLE_RURAL[0], real_rows_table)
    assert f["is_oz2_nomination_eligible"] is False
    assert f["is_oz2_nomination_eligible"] is not None


def test_g1_nomination_none_cause_a_absent_from_treasurys_universe(real_rows_table):
    """None cause (a): the GEOID has no row in Treasury's 85,529-row universe.

    THE MUTATION THE PROMPT NAMES: make the absent branch return False. That is
    the fabricated negative this package exists to close, and it reddens here.
    """
    f = _oz2_flags("99999999999", real_rows_table)
    assert f["is_oz2_nomination_eligible"] is None
    assert f["is_oz2_nomination_eligible"] is not False


def test_g1_nomination_none_cause_b_key_on_a_different_scheme(real_rows_table):
    """None cause (b): the GEOID is real, but keyed on the scheme Treasury does
    not use — a Connecticut LEGACY county key. Distinct from (a) in CAUSE even
    though both yield None, which is why they are two gates and why the status
    string separates them.

    Mutation: drop the CT_LEGACY_COUNTY_PREFIXES branch from _oz2_flags so the
    key merely falls through to the absent branch -> the status assertion below
    reddens (the value stays None, which is exactly why asserting only the value
    would be a vacuous gate).
    """
    f = _oz2_flags(REAL_CT_LEGACY_ABSENT, real_rows_table)
    assert f["is_oz2_nomination_eligible"] is None
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    r = m.check_tract(REAL_CT_LEGACY_ABSENT)
    assert r.oz2_nomination_status == "refused-connecticut-scheme"
    assert r.oz2_nomination_status != "not-determined"


def test_g1_rural_true_and_false(real_rows_table):
    """Mutation: collapse rural to True-only (oz-tracker's answer space) -> red."""
    assert _oz2_flags(REAL_ELIGIBLE_RURAL[0], real_rows_table)["is_rural_area_qoz_eligible"] is True
    assert _oz2_flags(REAL_ELIGIBLE_NONRURAL[0], real_rows_table)["is_rural_area_qoz_eligible"] is False


def test_g1_rural_none_cause_a_absent(real_rows_table):
    f = _oz2_flags("99999999999", real_rows_table)
    assert f["is_rural_area_qoz_eligible"] is None


def test_g1_rural_none_cause_b_wrong_scheme(real_rows_table):
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    r = m.check_tract(REAL_CT_LEGACY_ABSENT)
    assert r.is_rural_area_qoz_eligible is None
    assert r.rural_area_qoz_status == "refused-connecticut-scheme"


# ══════════════════════════════════════════════════════════════════════════════
# GATE 2 — the rural restriction, on a REAL row.
# ══════════════════════════════════════════════════════════════════════════════

def test_g2_rural_flag_is_none_for_an_ineligible_tract_treasury_flagged_rural(real_rows_table):
    """01001020100 is a REAL Treasury row: eligible_lic = 0, rural_status = 1.

    It must return None, never True. Treasury populates rural_status for all
    85,529 rows but determines rural status over ELIGIBLE tracts only; a
    populated column is not a published determination.

    MUTATION: drop the `if is_elig` restriction in load_oz2_table so rural is
    `bool(row[rur_i])` unconditionally. This tract then returns True and this
    gate reddens — on Treasury's own row, not one written to suit.
    """
    geoid, lic, rural_col = REAL_INELIGIBLE_RURAL
    assert (lic, rural_col) == (0, 1), "specimen must be ineligible-but-rural-flagged"
    f = _oz2_flags(geoid, real_rows_table)
    assert f["is_oz2_nomination_eligible"] is False
    assert f["is_rural_area_qoz_eligible"] is None
    assert f["is_rural_area_qoz_eligible"] is not True


def test_g2_the_restriction_is_applied_in_the_loader_not_the_caller(real_rows_table):
    """Applied at the single point of construction, so no consumer can reach an
    unrestricted rural flag at all. Mutation: move the restriction into
    _oz2_flags and this reddens, because the TABLE would then carry True."""
    assert real_rows_table.loc[
        REAL_INELIGIBLE_RURAL[0], "oz2_rural_area_qoz"] is None


# ══════════════════════════════════════════════════════════════════════════════
# GATE 3 — the scheme discriminator (§6). DERIVED from data, asserted against
# the declaration. A declared-only discriminator certifies consistency, not truth.
# ══════════════════════════════════════════════════════════════════════════════

def test_g3_the_oz2_binding_refuses_a_table_on_the_legacy_scheme():
    """Feed the OZ binding a table carrying 09001 prefixes; it must refuse.

    MUTATION: make validate_table_scheme compare self.scheme to self.scheme (i.e.
    relax the derived check to the declared one). It then accepts anything and
    this gate reddens.
    """
    with pytest.raises(OZ2SchemaError) as e:
        OZ2_TRACT_BINDING.validate_table_scheme(["09001020100", "17031840100"])
    assert "scheme" in str(e.value).lower()
    assert TRACT_SCHEME_LEGACY_COUNTY in str(e.value)


def test_g3_a_legacy_binding_refuses_a_table_on_the_cog_scheme():
    """The mirror direction, so the gate cannot pass by always-refusing."""
    legacy = OZ2TractBinding(
        basis_year=2020, scheme=TRACT_SCHEME_LEGACY_COUNTY,
        table_geoid_header="census_tract_number", sheet_name="x",
    )
    with pytest.raises(OZ2SchemaError):
        legacy.validate_table_scheme(["09110415300", "17031840100"])
    # ...and accepts its own scheme, so refusal is not unconditional.
    assert legacy.validate_table_scheme(
        ["09001020100", "17031840100"]) == TRACT_SCHEME_LEGACY_COUNTY


def test_g3_the_real_oz2_binding_accepts_the_cog_scheme():
    assert OZ2_TRACT_BINDING.validate_table_scheme(
        ["09110415300", "17031840100"]) == TRACT_SCHEME_COG_PLANNING_REGION


def test_g3_basis_year_cannot_tell_the_two_tables_apart():
    """The finding that forces a separate binding: BOTH tables are 2020-basis and
    both say '2020'. If basis could discriminate, none of §6 would be needed."""
    from nmtcmapper.data.schema import TRACT_VINTAGE
    assert TRACT_VINTAGE.basis_year == OZ2_TRACT_BINDING.basis_year == 2020
    assert "2020" in TRACT_VINTAGE.table_geoid_header
    # ...and yet the two schemes are disjoint in Connecticut:
    assert not (CT_LEGACY_COUNTY_PREFIXES & CT_COG_COUNTY_PREFIXES)


def test_g3_an_underivable_table_is_refused_not_defaulted():
    """§11 warned CT prefixes could be fragile — 'a table with no CT rows, say'.
    That case is an ERROR, not a pass. Refusing to classify is the only answer
    that does not silently certify an unknown.

    Mutation: return TRACT_SCHEME_COG_PLANNING_REGION as a default when no CT
    rows are present -> red.
    """
    with pytest.raises(ValueError, match="no Connecticut rows"):
        derive_tract_scheme(["17031840100", "06037123400"])
    with pytest.raises(OZ2SchemaError):
        OZ2_TRACT_BINDING.validate_table_scheme(["17031840100"])


def test_g3_a_table_carrying_both_schemes_is_refused():
    with pytest.raises(ValueError, match="BOTH Connecticut schemes"):
        derive_tract_scheme(["09001020100", "09110415300"])


def test_g3_the_binding_refuses_an_undecidable_declaration():
    with pytest.raises(ValueError, match="Unknown tract scheme"):
        OZ2TractBinding(basis_year=2020, scheme="2020",
                        table_geoid_header="census_tract_number", sheet_name="x")


# ══════════════════════════════════════════════════════════════════════════════
# GATE 4 — Connecticut and the territories are refused LOUDLY, and the refusal
# is visible on the user-facing surface. A silent None for an entire state is the
# misdescription failure mode; gating only the VALUE would pass on a silent None.
# ══════════════════════════════════════════════════════════════════════════════

def test_g4_connecticut_refusal_is_on_the_user_facing_surface(real_rows_table, capsys):
    """MUTATION: change summary()'s refused-connecticut-scheme line to the
    generic 'NOT DETERMINED' text. The value stays None and every value-level
    assertion still passes — this gate is the only thing that reddens."""
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    r = m.check_tract(REAL_CT_LEGACY_ABSENT)
    r.summary()
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "Connecticut" in out
    # The remedy must be stated, not merely the refusal.
    assert "09110" in out and "09001" in out


def test_g4_every_ct_legacy_county_prefix_is_refused(real_rows_table):
    """All eight, not a sample — a loop over one prefix would pass while seven
    states-worth of tracts answered silently."""
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    seen = []
    for prefix in sorted(CT_LEGACY_COUNTY_PREFIXES):
        r = m.check_tract(prefix + "020100")
        seen.append(r.oz2_nomination_status)
    assert len(seen) == 8
    assert set(seen) == {"refused-connecticut-scheme"}


def test_g4_a_cog_keyed_connecticut_tract_gets_a_real_answer(real_rows_table):
    """The refusal is about the KEY's scheme, not about Connecticut. A CT tract
    supplied on Treasury's own scheme is answerable, and saying so is what makes
    the refusal message actionable rather than a dead end."""
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    r = m.check_tract(REAL_CT_COG_ELIGIBLE[0])
    assert r.is_oz2_nomination_eligible is True
    assert r.oz2_nomination_status == "eligible-for-nomination"


def test_g4_a_territory_tract_absent_from_the_nmtc_table_still_gets_an_oz2_answer(real_rows_table):
    """Guam has no row in the CDFI Fund NMTC table at all, so nmtc_eligible is
    None — but Treasury scored it, so the OZ 2.0 answer is real. The two sources
    are independent and this is the one place OZ 2.0 is MORE complete."""
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    r = m.check_tract(REAL_GUAM[0])
    assert r.nmtc_eligible is None and r.tract_found is False
    assert r.is_oz2_nomination_eligible is True


# ══════════════════════════════════════════════════════════════════════════════
# GATE 7 — the two OZ fields have opposite `False` semantics (prompt §7).
# ══════════════════════════════════════════════════════════════════════════════

def test_g7_oz1_false_is_never_returnable_and_oz2_false_is(real_rows_table):
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    r = m.check_tract(REAL_INELIGIBLE_RURAL[0])
    assert r.is_opportunity_zone is not False   # OZ 1.0: True or None, never False
    assert r.is_oz2_nomination_eligible is False  # OZ 2.0: False is a fact


def test_g7_the_no_inputs_zero_is_distinguishable_from_a_measured_zero(real_rows_table):
    """THE FINDING THIS RELEASE ADDS THAT THE METHODOLOGY DID NOT SEE.

    Treasury published eligible_lic = 0 for 1,080 tracts whose poverty_rate AND
    mfi_ratio are both blank — a 0 with no measurable input behind it. The value
    stays False (0 is what Treasury published), but a caller who must not act on
    an unmeasured negative has to be able to see the difference, and the boolean
    alone cannot show it.

    Mutation: drop oz2_inputs_missing from the status switch so both zeroes
    report 'ineligible-on-treasury-inputs' -> red.
    """
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    measured = m.check_tract(REAL_INELIGIBLE_RURAL[0])
    noinput = m.check_tract(REAL_INELIGIBLE_NOINPUT[0])
    assert measured.is_oz2_nomination_eligible is False
    assert noinput.is_oz2_nomination_eligible is False
    assert measured.oz2_nomination_status == "ineligible-on-treasury-inputs"
    assert noinput.oz2_nomination_status == "ineligible-no-inputs-published"
    assert measured.oz2_nomination_status != noinput.oz2_nomination_status


def test_g7_no_designation_is_asserted_anywhere_in_the_public_surface():
    """Nothing is designated and nothing can be before late 2026. No public name
    may say otherwise (methodology §1)."""
    from nmtcmapper.eligibility.checker import EligibilityResult
    import dataclasses
    names = [f.name for f in dataclasses.fields(EligibilityResult)]
    names += [a for a in dir(EligibilityResult) if not a.startswith("_")]
    offenders = [n for n in names if "oz2" in n.lower() and "designat" in n.lower()]
    assert offenders == []


def test_g7_summary_never_prints_a_bare_no_for_an_indeterminate_oz2_answer(real_rows_table, capsys):
    """The ternary trap, killed explicitly in the rendering and not only in the
    type — the human-readable block is what a user pastes into a memo."""
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    m.check_tract("99999999999").summary()
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if "OZ 2.0 Eligible:" in l][0]
    assert "NOT DETERMINED" in line
    assert "❌" not in line


# ══════════════════════════════════════════════════════════════════════════════
# Loader structural gates.
# ══════════════════════════════════════════════════════════════════════════════

def test_flag_allowlist_rejects_an_unrecognised_cell(tmp_path, monkeypatch):
    """A re-publish that changes a 1 to 'Y' passes every header check. 'Y' parses
    truthy but 'N' parses TRUTHY TOO under bool() — and a blank parses falsy,
    which is the fabricated-negative direction. Mutation: drop the allowlist
    check -> the bad value is accepted silently and this reddens."""
    import openpyxl
    from nmtcmapper.data import loader as L
    from nmtcmapper.data.schema import OZ2_EXPECTED_HEADERS, OZ2_SHEET
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = OZ2_SHEET
    ws.append(list(OZ2_EXPECTED_HEADERS))
    for i in range(1200):
        geoid = "09110%06d" % i if i < 3 else "17031%06d" % i
        ws.append([geoid, "S", "C", "", 10.0, 5, 5, 5, 5, 1.0, 1, 0])
    ws.cell(row=5, column=11).value = "Y"     # eligible_lic := "Y"
    p = tmp_path / "oz2.xlsx"; wb.save(p)
    monkeypatch.setattr(L, "download_oz2_file", lambda force=False: p)
    with pytest.raises(OZ2SchemaError, match="FABRICATED NEGATIVE"):
        L.load_oz2_table()


def test_header_guard_rejects_a_renamed_column(tmp_path, monkeypatch):
    import openpyxl
    from nmtcmapper.data import loader as L
    from nmtcmapper.data.schema import OZ2_EXPECTED_HEADERS, OZ2_SHEET
    hdr = list(OZ2_EXPECTED_HEADERS); hdr[10] = "eligible_lic_v2"
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = OZ2_SHEET
    ws.append(hdr); ws.append(["09110000100", "S", "C", "", 1.0, 5, 5, 5, 5, 1.0, 1, 0])
    p = tmp_path / "oz2.xlsx"; wb.save(p)
    monkeypatch.setattr(L, "download_oz2_file", lambda force=False: p)
    with pytest.raises(OZ2SchemaError, match="header mismatch"):
        L.load_oz2_table()


def test_row_floor_rejects_a_degenerate_parse(tmp_path, monkeypatch):
    import openpyxl
    from nmtcmapper.data import loader as L
    from nmtcmapper.data.schema import OZ2_EXPECTED_HEADERS, OZ2_SHEET
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = OZ2_SHEET
    ws.append(list(OZ2_EXPECTED_HEADERS))
    ws.append(["09110000100", "S", "C", "", 1.0, 5, 5, 5, 5, 1.0, 1, 0])
    p = tmp_path / "oz2.xlsx"; wb.save(p)
    monkeypatch.setattr(L, "download_oz2_file", lambda force=False: p)
    with pytest.raises(OZ2SchemaError, match="floor"):
        L.load_oz2_table()


def test_the_two_tables_are_never_merged():
    """Held as two attributes on two schemes. A single table would have to pick
    one CT scheme and silently lose the other."""
    m = NMTCMapper.from_sample()
    assert m._table is not m._oz2_table
    assert "oz2_nomination_eligible" not in m._table.columns
    assert "nmtc_eligible" not in m._oz2_table.columns


# ══════════════════════════════════════════════════════════════════════════════
# Gates added because a mutation ran GREEN against the first draft of this file.
# Each closes a hole that the gate above it was assumed — wrongly — to cover.
# ══════════════════════════════════════════════════════════════════════════════

def test_the_loader_actually_calls_the_scheme_validator(tmp_path, monkeypatch):
    """Gate 3 proved validate_table_scheme REFUSES. It did not prove the loader
    CALLS it, and deleting the call ran green across the whole suite — the gate
    certified a function, not the code path.

    MUTATION: replace `OZ2_TRACT_BINDING.validate_table_scheme(geoids)` in
    load_oz2_table with `pass` -> this reddens (and nothing else did).
    """
    from nmtcmapper.data import loader as L
    # A well-formed workbook in every respect EXCEPT that Connecticut is keyed on
    # the legacy scheme — i.e. the CDFI Fund's file shape, not Treasury's.
    rows = [("09001%06d" % i, 1, 0) for i in range(5)]
    rows += [("55025%06d" % i, 0, 0) for i in range(1200)]
    p = _write_oz2_workbook(tmp_path / "legacy.xlsx", rows)
    monkeypatch.setattr(L, "download_oz2_file", lambda force=False: p)
    with pytest.raises(OZ2SchemaError, match="scheme mismatch"):
        L.load_oz2_table()


def test_the_loader_refuses_a_workbook_with_no_connecticut_rows(tmp_path, monkeypatch):
    """The other half of the same hole: an underivable table must not load."""
    from nmtcmapper.data import loader as L
    rows = [("55025%06d" % i, 0, 0) for i in range(1200)]
    p = _write_oz2_workbook(tmp_path / "noct.xlsx", rows)
    monkeypatch.setattr(L, "download_oz2_file", lambda force=False: p)
    with pytest.raises(OZ2SchemaError, match="scheme"):
        L.load_oz2_table()


def test_the_live_constructor_sources_oz2_from_its_own_loader():
    """`test_the_two_tables_are_never_merged` runs on from_sample(), so rebinding
    `self._oz2_table = self._table` in __init__ ran GREEN. Source-level gate, the
    same idiom test_fabricated_negatives.py uses for the check_tract() branch:
    only NMTCMapper.__init__ can be checked without a network call, so check it.

    MUTATION: `self._oz2_table = self._table` in __init__ -> red.
    """
    import inspect
    from nmtcmapper.mapper import NMTCMapper
    body = inspect.getsource(NMTCMapper.__init__)
    assert re.search(r"self\._oz2_table\s*=\s*load_oz2_table\(", body), (
        "NMTCMapper.__init__ must source the OZ 2.0 table from load_oz2_table(). "
        "Any other source — including self._table — silently answers OZ 2.0 "
        "questions from a table on a different GEOID scheme."
    )
    assert not re.search(r"self\._oz2_table\s*=\s*self\._table", body)


def test_the_two_loaders_produce_disjoint_column_sets(real_rows_table):
    """No column name is shared, so neither frame can stand in for the other
    without an immediate KeyError."""
    from nmtcmapper.data.loader import load_sample_table
    assert not (set(real_rows_table.columns) & set(load_sample_table().columns))


def test_the_connecticut_summary_line_names_both_schemes_and_the_remedy(real_rows_table, capsys):
    """M4 first ran green because the mutation replaced only the first line of a
    four-line message. The gate must pin every load-bearing token separately, not
    a single substring that a partial edit leaves behind."""
    m = NMTCMapper.from_sample()
    m._oz2_table = real_rows_table
    m.check_tract(REAL_CT_LEGACY_ABSENT).summary()
    out = capsys.readouterr().out
    tokens = ("REFUSED", "Connecticut", "09001-09015", "09110-09190", "ZERO GEOIDs")
    assert len(tokens) == 5, "the loop below has no floor without this"
    for token in tokens:
        assert token in out, f"the Connecticut refusal no longer states {token!r}"


# ══════════════════════════════════════════════════════════════════════════════
# THE FIGURE MANIFEST, and the prose gates that ride on it.
#
# Every OZ 2.0 quantity this release publishes appears HERE and nowhere else as a
# literal. `tests/test_live_oz2_file.py` asserts this manifest against Treasury's
# real file; the gates below assert the README and the CHANGELOG against this
# manifest. Prose -> manifest -> Treasury. Neither link alone is worth anything,
# and the seam is stated rather than hidden.
#
# THE CHANGELOG IS GATED, NOT ONLY THE README. Every quantitative claim of a
# release cycle tends to live in the CHANGELOG, and the no-hand-typed-figures
# gate has historically covered only the README.
# ══════════════════════════════════════════════════════════════════════════════

OZ2_PUBLISHED_FIGURES = {
    "oz2_universe":         85_529,   # rows in Treasury's file
    "oz2_eligible":         25_332,   # eligible_lic == 1
    "oz2_ineligible":       60_197,   # eligible_lic == 0
    "oz2_rural_eligible":    8_334,   # eligible AND rural_status == 1
    "oz2_nonrural_eligible": 16_998,  # eligible AND rural_status == 0
    "oz2_rural_but_ineligible": 20_377,  # rural_status == 1, NOT eligible -> None
    "oz2_no_inputs":         1_080,   # published 0 with poverty AND mfi blank
    "oz2_no_inputs_reachable": 1_047,  # of those, present in the NMTC universe too
    "oz2_no_inputs_ordinary_codes": 259,  # of those, not a 98xx/99xx tract code
    "oz2_missing_mfi_but_eligible": 1_068,  # blank mfi_ratio, published ELIGIBLE
    "oz2_ct_tracts":           884,   # Connecticut rows in Treasury's file
    "oz2_ct_eligible":         243,   # of those, eligible
    "nmtc_ct_tracts":          883,   # Connecticut rows in the CDFI Fund table
    # The DECIA coverage boundary (0.6.0 hygiene). Territory tracts EXIST in
    # Treasury's OZ 2.0 universe and get real answers; they have no row in the
    # CDFI Fund's NMTC table at all. Both halves are gated live in
    # test_live_oz2_file.py — the zero especially, because a coverage claim
    # resting on one not-found specimen is an anecdote, not a measurement.
    "oz2_territory_tracts":    133,   # AS+GU+MP+VI rows in Treasury's file
    "oz2_territory_as":         18,   # American Samoa   (60)
    "oz2_territory_gu":         57,   # Guam             (66)
    "oz2_territory_mp":         26,   # N. Mariana Is.   (69)
    "oz2_territory_vi":         32,   # US Virgin Is.    (78)
    "nmtc_territory_tracts":     0,   # ALL FOUR, in the CDFI Fund table
    "nmtc_pr_tracts":          981,   # Puerto Rico IS covered — why 72 is excluded
}

_DOC_FILES = ("README.md", "CHANGELOG.md")


# The claims (j2) and (j3) forbid live in paragraphs that often never write the
# literal string "OZ 2.0" — the designation and nomination-window sentences say
# "2027 QOZ" and "nomination window". A detector keyed only on "OZ 2.0" skipped
# exactly those paragraphs, and the (j3) mutation ran GREEN against the first
# draft of this file for that reason. Widened, deliberately.
_OZ2_MARKERS = re.compile(
    r"OZ ?2\.0|oz2_|is_oz2|rural_area_qoz|2027 QOZ|nomination window|"
    r"nomination-eligib|1400Z|eligible_lic|Rev\. Proc\. 2026-14", re.I)


def _oz2_paragraphs(text):
    """Blocks of prose that concern OZ 2.0. Figures elsewhere in these files
    belong to other releases and are gated by their own suites."""
    return [b for b in re.split(r"\n\s*\n", text) if _OZ2_MARKERS.search(b)]


@pytest.mark.repo  # _DOC_FILES includes CHANGELOG.md, absent from the release jobs' run directory
@pytest.mark.parametrize("filename", _DOC_FILES)
def test_no_oz2_figure_is_hand_typed(filename):
    """(j1) Every 4-or-5-digit figure in an OZ 2.0 paragraph of the README or the
    CHANGELOG must be a value from the manifest.

    finditer, NOT search: `search` stops at the first match, so a document with
    one correct figure and nine wrong ones passes. That is the shape this gate
    keeps being written in, and it is why it is spelled out here.

    MUTATION: change any manifest value (e.g. oz2_eligible 25332 -> 25333)
    without touching the docs -> red.
    """
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / filename
    assert path.exists(), f"{filename} must ship beside tests/"
    allowed = {str(v) for v in OZ2_PUBLISHED_FIGURES.values()}
    allowed |= {f"{v:,}" for v in OZ2_PUBLISHED_FIGURES.values()}
    # County FIPS prefixes are DERIVED from the package's own constants, not
    # allow-listed by hand — the prose and the code then cannot drift apart.
    allowed |= CT_LEGACY_COUNTY_PREFIXES | CT_COG_COUNTY_PREFIXES
    # Years, statute cites and percentages are not table counts. `34235` is the
    # Federal Register page for Connecticut's county-equivalent renumbering
    # (87 FR 34235) — a citation, and the only bare number here that is one.
    allowed |= {"2020", "2024", "2026", "2027", "2010", "2018", "2025", "1400",
                # 2023: the CDFI Fund's Island Areas LIC file vintage
                # (2023-12-19). A publication date, not a table count.
                "2023",
                "0.70", "45", "125", "34235",
                # HTTP statuses in the exception-hierarchy diagram (and the
                # 200 the 0.6.1 pinned-URL gates require of OZ2_URL), and the
                # statutory "fewer than 100 LICs" threshold for the 25-tract
                # designation exception. None is a table count.
                "403", "404", "200", "100"}
    offenders = []
    for block in _oz2_paragraphs(path.read_text(encoding="utf-8")):
        # The suite-size paragraph is a TEST-COUNT claim, not a Treasury figure.
        # It has its own, stronger gate: docs-check's `readme-test-count` runs
        # pytest and compares the collection. Asserting it against the Treasury
        # manifest here would be asserting it against the wrong reality.
        if "tests across all modules" in block:
            continue
        for m in re.finditer(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{3,6}\b", block):
            if m.group(0) not in allowed:
                offenders.append((filename, m.group(0), block[:80].replace("\n", " ")))
    assert not offenders, (
        "figures in OZ 2.0 prose that are not in OZ2_PUBLISHED_FIGURES "
        f"(so nothing derives them from Treasury's file): {offenders}"
    )


@pytest.mark.repo  # CHANGELOG.md
@pytest.mark.parametrize("filename", _DOC_FILES)
def test_oz2_prose_never_calls_an_eligible_tract_designated(filename):
    """(j2) No tract is designated and none can be before late 2026. The prose
    must not say otherwise — a name or a sentence is read far more often than a
    docstring.

    MUTATION: write "designated as a 2027 QOZ" in the CHANGELOG's OZ 2.0 entry
    -> red.
    """
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / filename
    banned = re.compile(
        r"(is|are|be(?:comes?)?|were)\s+designated\s+(?:as\s+)?(?:a\s+)?2027",
        re.I)
    blocks = _oz2_paragraphs(path.read_text(encoding="utf-8"))
    # FLOOR, outside the loop: on an empty block list every assertion below is
    # skipped and this gate certifies nothing.
    assert blocks, f"{filename} mentions OZ 2.0 nowhere; this gate is vacuous"
    for block in blocks:
        hits = [m.group(0) for m in banned.finditer(block)]
        assert not hits, f"{filename} asserts a 2027 designation: {hits}"


@pytest.mark.repo  # CHANGELOG.md
@pytest.mark.parametrize("filename", _DOC_FILES)
def test_oz2_prose_does_not_say_the_window_closes_in_september(filename):
    """(j3) §1400Z-1(b)(2) survives OBBBA: a State CEO may request a 30-day
    extension of the determination period (to 2026-10-28) AND of the Secretary's
    consideration period (to 2026-12-28). Prose that asserts a September close is
    wrong.

    MUTATION: write "nominations close September 28, 2026" -> red.
    """
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / filename
    bad = re.compile(r"clos\w*\s+(?:on\s+)?(?:September|Sept\.?|2026-09)", re.I)
    blocks = _oz2_paragraphs(path.read_text(encoding="utf-8"))
    assert blocks, f"{filename} mentions OZ 2.0 nowhere; this gate is vacuous"
    for block in blocks:
        hits = [m.group(0) for m in bad.finditer(block)]
        assert not hits, (
            f"{filename} asserts the nomination window closes in September; the "
            f"§1400Z-1(b)(2) extensions run it to 2026-10-28 / 2026-12-28: {hits}"
        )


@pytest.mark.repo  # globs nmtcmapper/**/*.py from the checkout and reads CHANGELOG.md
def test_the_retired_nmtc_vocabulary_never_appears():
    """The current NMTC round runs on Severe Distress / Deep Distress with
    quantified commitments, NOT 'Areas of Higher Distress'. Gated across the
    whole package and both doc files.

    tests/ IS EXCLUDED — this module has to be able to hold the string it forbids,
    or the gate cannot name what it is forbidding.

    SCOPE, AND WHY IT IS NOT "the whole file". Two occurrences survive in the
    CHANGELOG's HISTORICAL entries and are deliberately not removed. One (0.4.3)
    is itself the correction — "Native Areas were categorised as *Areas of Higher
    Distress*. They are *Areas of Deep Distress*" — and deleting the phrase would
    delete the record of the fix. A changelog is a record of what was said, and
    silently editing a past entry to satisfy a present gate is a worse defect
    than the stale phrase. The gate therefore covers every LIVE surface (package
    source, README, and the CHANGELOG entry under development) and stops at the
    released-history boundary, which is stated here rather than left implicit.

    MUTATION: write "Areas of Higher Distress" into the 0.6.0 CHANGELOG entry or
    any nmtcmapper/*.py docstring -> red.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    targets = [root / "README.md"] + sorted(root.glob("nmtcmapper/**/*.py"))
    for p in targets:
        for m in re.finditer(r"Areas? of Higher Distress", p.read_text(
                encoding="utf-8", errors="replace"), re.I):
            offenders.append((str(p.relative_to(root)), m.group(0)))
    # The CHANGELOG, from the top down to the end of the entry under development.
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    live_entry = changelog.split("## [0.5.0]")[0]
    for m in re.finditer(r"Areas? of Higher Distress", live_entry, re.I):
        offenders.append(("CHANGELOG.md (0.6.0 entry)", m.group(0)))
    assert not offenders, f"retired NMTC vocabulary: {offenders}"


@pytest.mark.repo  # CHANGELOG.md
def test_column_two_is_never_called_the_lic_column_without_its_qualifier():
    """Column 2 was renamed upstream to '...on Poverty or Income Criteria OR HIGH
    MIGRATION RURAL Census Tract?' — a SEMANTIC rename. Prose calling it 'the LIC
    column' without the qualifier is wrong."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    bad = re.compile(r"column\s+(?:2|C|two)\b[^.\n]{0,40}\bthe LIC column", re.I)
    assert len(_DOC_FILES) == 2, "the loop below has no floor without this"
    for name in _DOC_FILES:
        text = (root / name).read_text(encoding="utf-8")
        assert not list(bad.finditer(text)), f"{name} calls column 2 'the LIC column'"


def test_the_oz2_decision_document_ships_and_is_reachable():
    """The governing document ships in BOTH artifacts, like
    fabricated_negatives.md. MANIFEST.in states the rule this satisfies: "A
    decision document that ships in only one artifact is one an installer can be
    missing without noticing." It was untracked entirely before this release."""
    from nmtcmapper import get_methodology_path
    p = get_methodology_path("oz2_nomination_eligibility.md")
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    # The three rulings this release implements, so a truncated or replaced file
    # cannot pass by merely existing.
    assert "is_oz2_designated" in text          # §1: not proposed
    assert "Scheme strictly dominates basis" in text   # §2
    assert "5.04" in text                       # §3: the Appendix is not exhaustive
    assert len(text.splitlines()) > 500
