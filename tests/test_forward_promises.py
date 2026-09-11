"""FIX4 F2 — a version-numbered promise in shipped documentation comes due.

RULE: a version-numbered promise in shipped documentation is a contract that
comes due on a date. Nothing in this repo gated it, and the release it names is
exactly the release nobody re-reads it in. 0.6.0 was about to ship a README —
in the wheel and on the PyPI page — saying *"Pass `str(geoid).zfill(11)` until
**0.6.0** normalizes it"* and *"`opportunity_zone_status` says `not-confirmed`
for input that was never a GEOID ... **0.6.0.**"*, and 0.6.0 does neither. The
same shape had already happened once: `census.py` carried "planned for 0.4.1"
through 0.4.1 and 0.4.2, and 0.5.0 corrected it to 0.6.0 — which then shipped
without it too.

This gate reads the version being built from pyproject.toml (never hard-coded)
and fails when README.md or any docs/ page mentions THAT version in a sentence
that is not a release note. Any mention of the build version or later is a
FORWARD REFERENCE; it is allowed only when the sentence is past-tense about a
shipped change ("added in 0.6.0", "removed in 0.6.0", "(0.6.0)"), or when it
names a LATER version — a promise that has not come due yet. The default is
to fail: a promise shaped in a way this gate did not anticipate is still a
promise, and the fix is to write the release note, not to teach the gate a new
way to say "later".

(j4): the docs must be located and non-empty, the number of docs scanned is
floored, and the detector is proven on synthetic sentences so a regex that
matched nothing could not pass by vacuity.

Scope: README.md and docs/*.md — the pages that ship and are read. The
methodology documents under nmtcmapper/methodology/ are DATED decision records
("nmtc-mapper 0.5.0 — ..."); their forward references are history and are not
scanned. Docstrings are not scanned here; the one forward promise a docstring
carried (census.py, per-row failure capture) was found by the FIX4 sweep and
retargeted by hand.
"""
import pathlib
import re
import sys

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None

ROOT = pathlib.Path(__file__).resolve().parent.parent

_DOC_PAGES_FLOOR = 4          # README + at least three docs/ pages

# X.Y.Z not embedded in a longer dotted token ("1.2.3.4", "v0.6.0rc1"); a
# sentence-ending period after it is allowed ("**0.6.0.**").
_VERSION = re.compile(r"(?<![\w.])(\d+)\.(\d+)\.(\d+)(?!\w|\.\d)")

# A version mention that describes a SHIPPED change, not a promise: a
# past-tense cue immediately before the number, or the number parenthesised
# as a "since" marker. Anything else that names the build version fails.
_PAST_TENSE_BEFORE = re.compile(
    r"\b(?:added|removed|introduced|changed|fixed|corrected|renamed|dropped|"
    r"deleted|deprecated|restored|new|since|as of|shipped|shipping|released)"
    r"\s+(?:in\s+|with\s+)?(?:\*{1,2}|`)?$", re.I)
_PARENTHESISED = re.compile(r"\(\s*(?:\*{1,2}|`)?$")


def build_version():
    """The version being built, from pyproject.toml — never typed here."""
    if tomllib is None:  # pragma: no cover
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        assert m, "pyproject.toml has no version"
        raw = m.group(1)
    else:
        with open(ROOT / "pyproject.toml", "rb") as fh:
            raw = tomllib.load(fh)["project"]["version"]
    m = _VERSION.fullmatch(raw)
    assert m, f"pyproject version {raw!r} is not X.Y.Z"
    return tuple(int(x) for x in m.groups())


def _sentences(text):
    """Paragraphs first, then hard-wrapping collapsed, then sentence-ending
    punctuation. A version is judged with its own sentence only."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        flat = re.sub(r"\s+", " ", para).strip()
        out.extend(s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z*`\"(>])", flat)
                   if s.strip())
    return out


def _is_release_note(sentence, start):
    """True when the version at `start` is the object of a past-tense cue
    ("removed in 0.5.0", "(0.5.0)"), i.e. a statement about what shipped."""
    before = sentence[:start]
    return bool(_PAST_TENSE_BEFORE.search(before) or _PARENTHESISED.search(before))


def forward_references(text, build):
    """Every version mention >= `build`, as (version tuple, sentence, is_promise).
    `is_promise` is True for a mention of the build version itself that is not
    a release note — the shape that has come due."""
    out = []
    for sentence in _sentences(text):
        for m in _VERSION.finditer(sentence):
            v = tuple(int(x) for x in m.groups())
            if v < build:
                continue
            promise = (v == build) and not _is_release_note(sentence, m.start())
            out.append((v, sentence.strip(), promise))
    return out


def _doc_pages():
    pages = [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md"))
    assert len(pages) >= _DOC_PAGES_FLOOR, (
        f"located only {len(pages)} doc pages; the gate below is vacuous under "
        f"{_DOC_PAGES_FLOOR}")
    return pages


# ── the detector is proven before it is trusted ───────────────────────────────

def test_the_detector_flags_a_promise_naming_the_build_version():
    build = (0, 6, 0)
    promise = "Pass `str(geoid).zfill(11)` until **0.6.0** normalizes it."
    refs = forward_references(promise, build)
    assert refs and refs[0][0] == build and refs[0][2] is True
    bare = "so junk input takes the `not-confirmed` branch. **0.6.0.**"
    refs = forward_references(bare, build)
    assert refs and refs[0][2] is True
    possessive = "Per-row failure capture is **0.6.0's**."
    refs = forward_references(possessive, build)
    assert refs and refs[0][2] is True


def test_the_detector_passes_a_release_note_and_a_later_version():
    build = (0, 6, 0)
    for note in ("`not-covered-territory` was added in 0.6.0.",
                 "**`pct_eligible` was removed in 0.6.0 and now raises.**",
                 "Removed in **0.6.0**: the alias.",
                 "The vocabulary (0.6.0) is exported."):
        refs = forward_references(note, build)
        assert len(refs) == 1, note
        assert refs[0][2] is False, note
    later = "Pass `str(geoid).zfill(11)` until **0.7.0** normalizes it."
    refs = forward_references(later, build)
    assert refs == [((0, 7, 0), later, False)]
    assert forward_references("removed in 0.5.0.", build) == []


# ── the gate ──────────────────────────────────────────────────────────────────

def test_the_build_version_is_read_from_pyproject():
    v = build_version()
    assert len(v) == 3 and v > (0, 0, 0)


@pytest.mark.repo  # docs/*.md are not in the release jobs' run directory
def test_no_shipped_doc_promises_the_version_being_built():
    """MUTATION: put "until **<build version>** normalizes it" back into the
    README's Known limitations -> red here, naming README.md.

    Page discovery happens HERE, not at collection time: CI's docs-check job
    collects this suite from a copy that carries README.md but no docs/*.md,
    and a floor that fires during collection breaks every count in that job
    (found by the very exit-status check FIX4 F7 added to docs_check.py)."""
    build = build_version()
    pages = _doc_pages()
    due = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert text.strip(), f"{page.name} is empty — not a pass"
        for v, sentence, promise in forward_references(text, build):
            if promise:
                due.append(f"{page.relative_to(ROOT).as_posix()}: {sentence}")
    assert len(pages) >= _DOC_PAGES_FLOOR
    assert not due, (
        f"shipped docs name the version being built ({'.'.join(map(str, build))}) "
        f"as a promise it does not keep — write the release note or retarget:"
        f"\n  - " + "\n  - ".join(due))


@pytest.mark.repo  # same: floors _doc_pages(), which reads docs/*.md
def test_the_scan_actually_read_versions_somewhere():
    """(j4) a detector that matched no version at all would pass every page."""
    total = sum(len(_VERSION.findall((p).read_text(encoding="utf-8")))
                for p in _doc_pages())
    assert total >= 3, f"only {total} version mentions across the doc pages"
