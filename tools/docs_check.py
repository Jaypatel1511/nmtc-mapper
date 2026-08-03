#!/usr/bin/env python3
"""docs_check.py — a README gate that consumes the artifact it certifies.

Design principle, stated once and applied everywhere below:

    A gate that cannot fail is worse than no gate, because it converts an
    unknown into a false assurance.

Concretely that means this script fails closed on every ambiguity:

  * It refuses to run unless the package resolves out of site-packages. If it
    ran against the checkout it would repeat the exact bug it exists to catch
    (release.yml's version check imported ./nmtcmapper and called it "verified
    the wheel" -- see release.yml's `docs-check` job comment).

    Worth being precise about the mechanism, since imprecision here is how the
    original bug survived review: `python tools/docs_check.py` puts the SCRIPT's
    directory (tools/) on sys.path[0], NOT the cwd -- so merely running this
    from the checkout root does not by itself import source. The cwd lands on
    sys.path when you use `python -c` or `python -m`, which is exactly what
    release.yml's old version check did. PYTHONPATH=., an editable install, or
    copying this script to the repo root will also shadow site-packages. The
    check below covers all of those cases by asserting on the resolved origin
    rather than on how the interpreter was invoked. Verified to fire:
    `PYTHONPATH=. python tools/docs_check.py --root .` exits 2.
  * An unmarked README code block is a FAILURE, not skipped coverage.
  * Zero executable blocks is a FAILURE, not a silent pass.
  * A `skip` without a reason is a FAILURE.
  * A known-failure ledger entry that has started passing is a FAILURE, so the
    ledger cannot silently accumulate dead weight.

Both README code-block styles are supported -- fenced (```python) and indented
(4 spaces OR a tab) -- because the portfolio is split almost exactly in half
between them. A checker that only parsed fences would report PASS with zero
coverage on the eleven indented-style repos, which is the same class of defect
as a version check that imports source.

Because indented blocks carry no info string, the run/skip marker is a comment
on the block's first line. One mechanism, both styles.

THE SIX ASSERTIONS
------------------
  1. Every block marked `run` produces exactly its committed stdout.
  2. Every symbol a block names as importable actually imports (README ->
     package: catches DRIFT).
  3. Any "N tests" claim in the README matches what pytest collects.
  4. No retired claim from the denylist survives in README/setup.py/pyproject
     description+keywords.
  5. Precondition: the package resolves out of site-packages, not the checkout.
  6. Every name in `__all__` appears somewhere in the README (package ->
     README: catches OMISSION).

Assertion 6 exists because 1-5 all run in the README -> package direction. They
can only catch the README claiming something false. They are structurally blind
to the README failing to mention a public symbol at all -- and on this repo
every real documentation defect was an omission or a prose claim, which is how
an all-green gate coexisted with nine of them.

BLOCK STYLES, INCLUDING THE ONE THAT SURPRISED US
-------------------------------------------------
Three styles reach the extractor, not two:

  * fenced with a language tag   -- ```python, ```bash
  * fenced with NO language tag  -- a bare ``` .
  * indented by 4 spaces or by a tab.

INTENDED BEHAVIOUR FOR AN UNTAGGED FENCE: it is extracted, and it requires a
marker, exactly like any other block. This is deliberate. The alternative --
skipping fences that carry no language tag -- would silently drop real
documented content and hand back a green check with no coverage over it, which
is the defect class this tool exists to refuse. Fail closed, as everywhere else.

This is live, not hypothetical, and the shape of it is worth recording because
two earlier descriptions of it were wrong. MEASURED on nmtc-screener's README
(the repo an earlier portfolio scan wrote off as "prose-only" because it
grepped for ```python): 12 fence LINES, which is 6 blocks, not 12. Five carry
```bash. Exactly ONE is a bare fence, and it is not shell -- it is 39 lines of
SAMPLE PROGRAM OUTPUT, a rendered screening report. Adoption there costs 6
markers, not 12.

That one block exposes a real tension worth knowing before the next adoption:
the marker is the block's first BODY line, so on an output block it is visible
to every reader of the rendered README. Inside ```bash a `#` marker is valid
shell and reads as a comment; inside a sample-output block it is simply noise
in the middle of the documented output. The mechanism is still correct -- fail
closed beats silently uncovered -- but a repo that documents output in bare
fences pays for the gate in rendered-doc cleanliness, and that trade should be
made deliberately rather than discovered.

KNOWN LIMITATIONS (recorded, not fixed -- adversarial-only, zero live
occurrences measured across 25 portfolio READMEs):

  * Code fenced INSIDE a blockquote ("> ```python") is not extracted.
  * Code nested inside a list item is treated as list continuation, not code
    (see _is_list_continuation).
  * `>>>` doctest / pycon blocks are not executed as doctests.

Each of these fails OPEN -- the block is invisible rather than misread -- so
they are coverage gaps, not false assurances. They are written down here rather
than left undiscovered, because an undocumented gap is indistinguishable from a
gap nobody knows about. Run --list-blocks to see exactly what was extracted.

Usage:
    python tools/docs_check.py [--root DIR] [--list-blocks] [--allow-source]

Exit status: 0 = pass, 1 = failure, 2 = configuration error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.9/3.10
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover
        sys.stderr.write(
            "docs-check: needs Python >=3.11 (tomllib) or the `tomli` package.\n"
        )
        raise SystemExit(2)


MARKER_RE = re.compile(r"^#\s*docs-check:\s*(run|skip)\b[ \t]*(.*)$")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})[ \t]*(\S*)")
FENCE_CLOSE_RE = re.compile(r"^(`{3,}|~{3,})[ \t]*$")
LIST_ITEM_RE = re.compile(r"^ {0,3}([-*+]|\d+[.)])[ \t]+")


# --------------------------------------------------------------------------
# Block extraction
# --------------------------------------------------------------------------


@dataclass
class Block:
    index: int              # 1-based, over every block found, both styles
    style: str              # "fenced" | "indented"
    info: Optional[str]     # fenced info string, else None
    line_no: int            # 1-based line of the first body line
    body: List[str]         # dedented body lines

    # populated by parse_marker
    action: Optional[str] = None      # "run" | "skip"
    argument: str = ""                # expected-file name (run) or reason (skip)

    @property
    def text(self) -> str:
        return "\n".join(self.body)

    @property
    def has_marker(self) -> bool:
        """True if body[0] is actually a docs-check marker line."""
        return bool(self.body) and MARKER_RE.match(self.body[0].strip()) is not None

    @property
    def code(self) -> str:
        """Body with the marker line removed -- what actually executes.

        Conditional on a marker actually being present. Dropping body[0]
        unconditionally silently ate the first real line of any UNMARKED block.
        That is masked on the failure path (unmarked blocks fail anyway), but it
        corrupts --list-blocks and every coverage number derived from it -- it
        made the audit's own first measurement of this tool wrong.
        """
        return "\n".join(self.body[1:] if self.has_marker else self.body)

    def label(self) -> str:
        return f"block {self.index} ({self.style}, README.md:{self.line_no})"


def _expand_leading_tabs(line: str, tabstop: int = 4) -> str:
    """Expand a line's LEADING whitespace run, tabs included, to spaces.

    CommonMark treats a tab as advancing to the next multiple of four, and a
    tab-indented block is a code block just like a 4-space one. The indent
    arithmetic everywhere below counts spaces, so a single tab measured as
    indent 0 and the whole block vanished -- no error, no coverage, green check.
    Measured zero times across 25 portfolio READMEs, but it is one keystroke
    away and free to close.

    Only the leading run is rewritten, so tabs inside string literals or in
    trailing alignment survive byte-for-byte.
    """
    col = 0
    for i, ch in enumerate(line):
        if ch == "\t":
            col += tabstop - (col % tabstop)
        elif ch == " ":
            col += 1
        else:
            return " " * col + line[i:]
    return " " * col


def _consume_indented(lines: Sequence[str], start: int) -> Tuple[List[str], int]:
    """Collect a 4-space indented block starting at `start`. Returns (body, end)."""
    body: List[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            body.append("")
            i += 1
            continue
        if len(line) - len(line.lstrip(" ")) >= 4:
            body.append(line[4:])
            i += 1
            continue
        break
    while body and body[-1].strip() == "":
        body.pop()
    return body, i


def _is_list_continuation(lines: Sequence[str], idx: int) -> bool:
    """True if the indented run at `idx` is list-item content, not a code block.

    CommonMark indents list continuation paragraphs too. Walking back to the
    nearest non-blank line and asking "was that a list item?" is enough for the
    READMEs in this portfolio, and erring toward "not code" here is safe only
    because every block this DOES extract must carry a marker -- a real block
    that got misclassified would show up as lost coverage in --list-blocks,
    which is why that mode exists.
    """
    j = idx - 1
    while j >= 0 and lines[j].strip() == "":
        j -= 1
    if j < 0:
        return False
    return bool(LIST_ITEM_RE.match(lines[j]))


def extract_blocks(text: str) -> List[Block]:
    """Extract code blocks in every supported style, in document order.

    Fenced blocks are recognised whether or not they carry a language tag; see
    the module docstring for why an untagged fence is treated as code rather
    than skipped.
    """
    # Normalise leading tabs first so every indent measurement below is in
    # spaces and tab-indented blocks are seen at all (see _expand_leading_tabs).
    lines = [_expand_leading_tabs(ln) for ln in text.split("\n")]
    blocks: List[Block] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        # --- fenced ---------------------------------------------------
        m = FENCE_RE.match(stripped)
        if m and indent <= 3:
            fence = m.group(1)
            info = m.group(2)
            body: List[str] = []
            j = i + 1
            closed = False
            while j < n:
                cand = lines[j].lstrip(" ")
                cand_indent = len(lines[j]) - len(cand)
                cm = FENCE_CLOSE_RE.match(cand)
                if (
                    cm
                    and cm.group(1)[0] == fence[0]
                    and len(cm.group(1)) >= len(fence)
                    and cand_indent <= 3
                ):
                    closed = True
                    break
                body.append(lines[j][indent:] if len(lines[j]) > indent else lines[j].lstrip(" "))
                j += 1
            while body and body[-1].strip() == "":
                body.pop()
            blocks.append(
                Block(
                    index=len(blocks) + 1,
                    style="fenced",
                    info=info or "",
                    line_no=i + 2,
                    body=body,
                )
            )
            i = j + 1 if closed else j
            continue

        # --- 4-space indented -----------------------------------------
        if indent >= 4 and stripped != "":
            prev_blank = (i == 0) or (lines[i - 1].strip() == "")
            if prev_blank and not _is_list_continuation(lines, i):
                body, end = _consume_indented(lines, i)
                if body:
                    blocks.append(
                        Block(
                            index=len(blocks) + 1,
                            style="indented",
                            info=None,
                            line_no=i + 1,
                            body=body,
                        )
                    )
                i = end
                continue

        i += 1

    return blocks


def parse_marker(block: Block) -> Optional[str]:
    """Attach the run/skip marker to `block`. Returns an error string or None."""
    if not block.body:
        return f"{block.label()}: empty block"
    first = block.body[0].strip()
    m = MARKER_RE.match(first)
    if not m:
        return (
            f"{block.label()}: missing marker. Every code block must begin with\n"
            f"      '# docs-check: run' or '# docs-check: skip <reason>'.\n"
            f"      First line was: {first!r}"
        )
    block.action = m.group(1)
    block.argument = m.group(2).strip()
    if block.action == "skip" and not block.argument:
        return (
            f"{block.label()}: 'skip' requires a reason -- "
            f"'# docs-check: skip <why this cannot run in CI>'"
        )
    return None


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    fid: str
    message: str


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def fail(self, fid: str, message: str) -> None:
        self.findings.append(Finding(fid, message))

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def ids(self) -> List[str]:
        return [f.fid for f in self.findings]


def slug(text: str, limit: int = 40) -> str:
    """A finding-id fragment that is readable AND unambiguous.

    The bare `s[:limit]` this replaces was not a cosmetic choice. Two denylist
    terms whose slugs shared a 40-character prefix collapsed to ONE finding id,
    so a single ledger entry written for one of them silently suppressed the
    others -- a ledger entry granting an exemption it was never reviewed for.
    Demonstrated on the seeded term's own family:

        'the methodology federal examiners use to grade banks'  ->
        'the methodology federal examiners use to assess CRA'   ->
            both slugged to 'the-methodology-federal-examiners-use-to'

    and one [[known_failures]] entry took both out, EXIT=0. The denylist is
    explicitly designed to travel across 22 repos and grow, so prefix collision
    is a question of when, not whether.

    Long terms now keep a readable prefix plus a digest of the FULL term, so
    ids stay greppable without ever being ambiguous.
    """
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) <= limit:
        return s
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{s[:limit - 9].rstrip('-')}-{digest}"


# --------------------------------------------------------------------------
# Assertion 5 (precondition): we are testing the installed artifact
# --------------------------------------------------------------------------


def resolve_packages(import_names: Sequence[str], allow_source: bool) -> List[object]:
    """Resolve and vet EVERY configured import name.

    [package].import_name accepts a list because a single distribution can ship
    more than one documented import path, and checking only one leaves the other
    unverified while the gate reports green. hmda-analyzer -- next but one in the
    adoption queue -- ships both `hmdaanalyzer` and `hmda_analyzer`, both
    documented and both working, so whichever you configured, the other went
    unchecked. A scalar string is still accepted and means a one-element list.
    """
    mods: List[object] = []
    for import_name in import_names:
        try:
            mod = importlib.import_module(import_name)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"docs-check: cannot import '{import_name}': {exc}\n"
                f"  The package must be INSTALLED before this gate runs.\n"
            )
            raise SystemExit(2)

        origin = getattr(mod, "__file__", None) or "<unknown>"
        print(f"  package        : {import_name}")
        print(f"  import origin  : {origin}")

        if "/site-packages/" in origin.replace(os.sep, "/"):
            print("  artifact       : installed distribution  [OK]")
        elif allow_source:
            print("  artifact       : SOURCE TREE (--allow-source given) [degraded]")
        else:
            sys.stderr.write(
                "\ndocs-check: FATAL -- import resolved to the source tree, not an\n"
                f"  installed distribution:\n    {origin}\n"
                "  Checking the source tree would repeat the exact defect this gate\n"
                "  exists to catch. Install the wheel and run from a directory that\n"
                f"  does not contain ./{import_name}, or pass --allow-source for local\n"
                "  development only.\n"
            )
            raise SystemExit(2)
        mods.append(mod)
    return mods


# --------------------------------------------------------------------------
# Assertion 1: executable blocks produce the documented output
# --------------------------------------------------------------------------


def expected_path(root: Path, expected_dir: str, block: Block) -> Path:
    name = block.argument or str(block.index)
    if not name.endswith(".txt"):
        name += ".txt"
    return root / expected_dir / name


def check_block_outputs(
    root: Path, expected_dir: str, blocks: List[Block], report: Report
) -> None:
    runnable = [b for b in blocks if b.action == "run"]

    if not runnable:
        # Fail-closed: "everything is skipped" must never read as "all green".
        report.fail(
            "no-executable-blocks",
            "zero README blocks are marked '# docs-check: run'. A gate with no\n"
            "      executable coverage cannot fail, so it is treated as a failure.\n"
            "      Mark at least one offline block 'run'.",
        )
        return

    # Same id-collision class as slug(): two run blocks pointing at one
    # expected-file name produced one shared finding id, so a ledger entry for
    # the first silently exempted the second. It is also a latent bug in its own
    # right -- both blocks get diffed against the same committed stdout -- so it
    # is reported rather than merely disambiguated.
    by_name: Dict[str, List[Block]] = {}
    for block in runnable:
        by_name.setdefault(expected_path(root, expected_dir, block).name, []).append(block)
    for name, sharing in by_name.items():
        if len(sharing) > 1:
            report.fail(
                f"readme-output-name-collision:{name}",
                f"{len(sharing)} run blocks share the expected-output file {name!r}: "
                + ", ".join(b.label() for b in sharing)
                + "\n      Give each 'run' block its own name: '# docs-check: run <name>'.",
            )

    for block in runnable:
        exp = expected_path(root, expected_dir, block)
        # Block index is part of the id so two blocks can never share one, even
        # while the collision above is being fixed.
        fid = f"readme-output:{block.index}:{exp.name}"

        if not exp.exists():
            report.fail(
                fid,
                f"{block.label()}: no expected-output file at {exp.relative_to(root)}\n"
                f"      Create it with the block's exact stdout so a diff is reviewable.",
            )
            continue

        # Execute from a scratch dir that contains no package source, so the
        # block imports the installed distribution -- same rule as the gate.
        with tempfile.TemporaryDirectory(prefix="docs-check-block-") as tmp:
            script = Path(tmp) / f"block_{block.index}.py"
            script.write_text(block.code + "\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, script.name],
                cwd=tmp,
                capture_output=True,
                text=True,
            )

        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()[-12:]
            report.fail(
                fid,
                f"{block.label()}: raised (exit {proc.returncode})\n"
                + "\n".join(f"      {ln}" for ln in tail),
            )
            continue

        actual = proc.stdout
        want = exp.read_text(encoding="utf-8")
        if actual != want:
            report.fail(
                fid,
                f"{block.label()}: stdout does not match "
                f"{exp.relative_to(root)}\n" + unified(want, actual),
            )
        else:
            report.note(f"{block.label()}: output matches {exp.relative_to(root)}")


def unified(want: str, actual: str) -> str:
    import difflib

    diff = difflib.unified_diff(
        want.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile="expected",
        tofile="actual",
    )
    return "".join(f"      {ln}" if not ln.endswith("\n") else f"      {ln}" for ln in diff).rstrip()


# --------------------------------------------------------------------------
# Assertion 2: every symbol the README names is importable
# --------------------------------------------------------------------------


def extract_symbols(blocks: Iterable[Block], import_name: str) -> List[Tuple[str, str, Block]]:
    """Return (module, symbol, block) for names the README claims exist.

    Deliberately narrow. Only two forms are trusted:
      * `from <pkg>[.sub] import X, Y`
      * `<pkg>.SYMBOL`
    Arbitrary identifiers (df.head(), locals, third-party calls) are NOT
    resolved -- breadth here would drown the signal in false positives.

    Runs over ALL blocks, including skipped ones. That is what gives coverage
    on a network-dependent Quickstart that can never execute in CI.
    """
    found: List[Tuple[str, str, Block]] = []
    seen = set()
    pkg_re = re.compile(
        r"^\s*from\s+(" + re.escape(import_name) + r"(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s+import\s+(.+)$"
    )
    attr_re = re.compile(r"\b" + re.escape(import_name) + r"\.([A-Za-z_][A-Za-z0-9_]*)")

    for block in blocks:
        code = block.code
        # Join parenthesised continuations so multi-line imports parse.
        joined = re.sub(r"\(\s*\n", "(", code)
        buf: List[str] = []
        for raw in joined.split("\n"):
            line = raw.rstrip()
            if line.endswith("\\"):
                buf.append(line[:-1])
                continue
            line = "".join(buf) + line
            buf = []

            m = pkg_re.match(line)
            if m:
                module, names = m.group(1), m.group(2)
                names = names.split("#")[0]
                names = names.replace("(", " ").replace(")", " ")
                for chunk in names.split(","):
                    name = chunk.strip().split(" as ")[0].strip()
                    if not name or name == "*":
                        continue
                    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                        continue
                    key = (module, name)
                    if key not in seen:
                        seen.add(key)
                        found.append((module, name, block))
                continue

            code_part = line.split("#")[0]
            for am in attr_re.finditer(code_part):
                name = am.group(1)
                key = (import_name, name)
                if key not in seen:
                    seen.add(key)
                    found.append((import_name, name, block))

    return found


def check_symbols(
    blocks: List[Block], import_names: Sequence[str], report: Report
) -> None:
    symbols: List[Tuple[str, str, Block]] = []
    seen = set()
    for import_name in import_names:
        for module_name, symbol, block in extract_symbols(blocks, import_name):
            if (module_name, symbol) not in seen:
                seen.add((module_name, symbol))
                symbols.append((module_name, symbol, block))

    if not symbols:
        report.note(
            "no symbols referenced in README blocks for "
            + "/".join(import_names)
        )
        return

    for module_name, symbol, block in symbols:
        fid = f"readme-symbol:{module_name}.{symbol}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            report.fail(
                fid,
                f"README names '{module_name}.{symbol}' ({block.label()}) but "
                f"module '{module_name}' does not import: {exc}",
            )
            continue
        if not hasattr(module, symbol):
            report.fail(
                fid,
                f"README names '{symbol}' as importable from '{module_name}' "
                f"({block.label()}), but it is not exported there.",
            )
        else:
            report.note(f"symbol {module_name}.{symbol} resolves")


# --------------------------------------------------------------------------
# Assertion 6: every public name in __all__ is mentioned in the README
# --------------------------------------------------------------------------


def check_all_documented(
    readme: str, import_names: Sequence[str], report: Report, enabled: bool = True
) -> None:
    """Assertion 6 -- the only assertion that runs package -> README.

    Assertions 1-5 all run README -> package. Every one of them starts from
    something the README says and asks whether the package agrees, so the whole
    set is structurally blind to the README simply NOT MENTIONING a public
    symbol. On this repo that blindness was the whole story: the gate was green
    with nine real README defects live, and every one of them was an omission or
    a prose claim rather than a false import.

    The test is deliberately weak: the name must appear SOMEWHERE in the README
    text -- prose, a code block, a bullet, anywhere. It does not ask for a
    signature, an example, or a section. A stronger check would be an opinion
    about documentation quality; this one is a fact about coverage, and a fact
    is what a gate can defend. Weak and true beats strong and arguable.

    Default ON. A repo that genuinely exports something it does not want
    documented says so in the ledger, where the claim is visible and owned.
    """
    if not enabled:
        report.note("assertion 6 (__all__ documented) disabled in config")
        return

    # Keyed on the SYMBOL, not on (symbol, package). "This name never appears in
    # the README" is a fact about the README, so it is one finding no matter how
    # many import paths export the name -- otherwise two documented import paths
    # would produce two findings sharing one id, which is exactly the ledger
    # over-suppression bug fixed in slug() and in the expected-file names.
    missing: Dict[str, List[str]] = {}
    checked: set = set()
    for import_name in import_names:
        try:
            mod = importlib.import_module(import_name)
        except Exception:  # noqa: BLE001 - resolve_packages already exited on this
            continue
        names = getattr(mod, "__all__", None)
        if not names:
            report.note(f"{import_name} defines no __all__ -- assertion 6 skipped")
            continue
        for name in names:
            checked.add(name)
            if re.search(r"\b" + re.escape(name) + r"\b", readme):
                continue
            missing.setdefault(name, []).append(import_name)

    for name, owners in missing.items():
        report.fail(
            f"readme-missing-symbol:{name}",
            f"{'/'.join(owners)}.__all__ exports '{name}' but the README never "
            f"mentions it. A public name the docs do not name is undiscoverable.",
        )

    if checked and not missing:
        report.note(
            f"all {len(checked)} __all__ export(s) are mentioned in the README"
        )


# --------------------------------------------------------------------------
# Assertion 3: any "N tests" claim matches collection
# --------------------------------------------------------------------------


def check_test_count(
    root: Path, readme: str, tests_path: str, pattern: str, report: Report
) -> None:
    claim_re = re.compile(pattern, re.MULTILINE)
    m = claim_re.search(readme)
    if not m:
        report.note("README makes no test-count claim (not a failure)")
        return

    claimed = int(m.group(1))
    tests_dir = root / tests_path
    if not tests_dir.exists():
        report.fail(
            "readme-test-count",
            f"README claims {claimed} tests but {tests_path} is not present to "
            f"collect from.",
        )
        return

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_path), "--collect-only", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    cm = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
    if not cm:
        cm = re.search(r"(\d+)/(\d+)\s+tests?\s+collected", proc.stdout)
        actual = int(cm.group(2)) if cm else None
    else:
        actual = int(cm.group(1))

    if actual is None:
        report.fail(
            "readme-test-count",
            "could not parse a collected-test count from pytest output:\n"
            + "\n".join(f"      {ln}" for ln in proc.stdout.splitlines()[-8:]),
        )
        return

    if claimed != actual:
        report.fail(
            "readme-test-count",
            f"README claims {claimed} tests; pytest collects {actual}.",
        )
    else:
        report.note(f"test-count claim {claimed} matches collection")


# --------------------------------------------------------------------------
# Assertion 4: no retired claim survives in metadata or prose
# --------------------------------------------------------------------------


def load_denylist(path: Path) -> List[str]:
    terms: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(line)
    return terms


def load_toml(path: Path, what: str) -> dict:
    """Parse TOML, or exit 2 -- the documented configuration-error status.

    An uncaught TOMLDecodeError exits 1 with a traceback, which makes a broken
    config indistinguishable from a documentation failure to any wrapper that
    reads exit codes -- and the docstring promises 2 means configuration error.
    A gate whose exit codes lie about the KIND of problem is a gate that gets
    retried instead of fixed.
    """
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        sys.stderr.write(f"docs-check: {what} at {path} is not valid TOML: {exc}\n")
        raise SystemExit(2)
    except OSError as exc:
        sys.stderr.write(f"docs-check: cannot read {what} at {path}: {exc}\n")
        raise SystemExit(2)


def pyproject_prose(path: Path) -> str:
    """Only the fields a reader actually sees: description + keywords."""
    data = load_toml(path, "pyproject.toml")
    project = data.get("project", {})
    parts: List[str] = []
    if isinstance(project.get("description"), str):
        parts.append(project["description"])
    kw = project.get("keywords")
    if isinstance(kw, list):
        parts.extend(str(k) for k in kw)
    return "\n".join(parts)


def check_denylist(
    root: Path, terms: Sequence[str], targets: Sequence[str], report: Report
) -> None:
    for target in targets:
        path = root / target
        if not path.exists():
            report.note(f"denylist target {target} absent -- skipped")
            continue
        if target == "pyproject.toml":
            haystack = pyproject_prose(path)
            where = "pyproject.toml [project].description/keywords"
        else:
            haystack = path.read_text(encoding="utf-8")
            where = target

        low = haystack.lower()
        for term in terms:
            if term.lower() in low:
                line_no = None
                for i, ln in enumerate(haystack.splitlines(), 1):
                    if term.lower() in ln.lower():
                        line_no = i
                        break
                loc = f"{where}:{line_no}" if line_no else where
                report.fail(
                    f"denylist:{slug(term)}:{target}",
                    f"retired claim {term!r} still present in {loc}",
                )


# --------------------------------------------------------------------------
# Known-failures ledger
# --------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    fid: str
    reason: str
    owner_release: str


def load_ledger(config: dict) -> List[LedgerEntry]:
    entries: List[LedgerEntry] = []
    for raw in config.get("known_failures", []) or []:
        fid = raw.get("id")
        reason = raw.get("reason")
        owner = raw.get("owner_release")
        if not fid or not reason or not owner:
            sys.stderr.write(
                "docs-check: every known_failures entry needs id, reason and "
                f"owner_release; got {raw!r}\n"
            )
            raise SystemExit(2)
        entries.append(LedgerEntry(fid, reason, owner))
    return entries


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="README gate for the CDFI portfolio")
    ap.add_argument("--root", default=".", help="directory holding docs-check.toml")
    ap.add_argument("--config", default="docs-check.toml")
    ap.add_argument("--list-blocks", action="store_true", help="print blocks and exit")
    ap.add_argument(
        "--allow-source",
        action="store_true",
        help="permit running against the source tree (local dev only)",
    )
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg_path = root / args.config
    if not cfg_path.exists():
        sys.stderr.write(f"docs-check: no config at {cfg_path}\n")
        return 2
    config = load_toml(cfg_path, "config")

    pkg_cfg = config.get("package", {})
    raw_import = pkg_cfg.get("import_name")
    readme_name = pkg_cfg.get("readme", "README.md")

    # Scalar or list -- a distribution may document more than one import path.
    if isinstance(raw_import, str):
        import_names = [raw_import]
    elif isinstance(raw_import, list):
        import_names = [x for x in raw_import if isinstance(x, str) and x]
        if len(import_names) != len(raw_import):
            sys.stderr.write(
                "docs-check: [package].import_name list must contain only "
                f"non-empty strings; got {raw_import!r}\n"
            )
            return 2
    else:
        import_names = []
    if not import_names:
        sys.stderr.write(
            "docs-check: [package].import_name is required (a string, or a list "
            "of strings when the distribution documents several import paths)\n"
        )
        return 2

    readme_path = root / readme_name
    if not readme_path.exists():
        sys.stderr.write(f"docs-check: no README at {readme_path}\n")
        return 2
    readme = readme_path.read_text(encoding="utf-8")

    print("=" * 72)
    print("docs-check")
    print("=" * 72)
    print(f"  root           : {root}")
    print(f"  readme         : {readme_name}")

    blocks = extract_blocks(readme)

    if args.list_blocks:
        # The diagnostic the module docstring points at, so it has to show the
        # things that actually go wrong: whether a marker was recognised (an
        # unmarked block is a failure, and used to have its first line eaten)
        # and how many lines would really execute.
        print(f"\n{len(blocks)} block(s) extracted:\n")
        for b in blocks:
            parse_marker(b)
            if b.style == "fenced":
                info = f" info={b.info!r}" if b.info else " info='' (BARE FENCE)"
            else:
                info = ""
            marker = f"{b.action}" if b.action else "NONE (would FAIL)"
            exec_lines = len([ln for ln in b.code.split("\n") if ln.strip()])
            print(f"  [{b.index}] {b.style:<8} line {b.line_no:<4}{info}")
            print(f"       marker    : {marker}"
                  + (f" -> {b.argument!r}" if b.argument else ""))
            print(f"       code lines: {exec_lines}")
            print(f"       first line: {(b.body[0] if b.body else '')[:70]!r}")
        return 0

    resolve_packages(import_names, args.allow_source)
    print()

    report = Report()

    if not blocks:
        report.fail(
            "no-code-blocks",
            "no code blocks found in the README at all. Either the README has no\n"
            "      examples, or the extractor failed -- both are failures for a gate\n"
            "      whose job is to check examples.",
        )

    for block in blocks:
        err = parse_marker(block)
        if err:
            report.fail(f"block-unmarked:{block.index}", err)

    marked = [b for b in blocks if b.action]
    print(f"  blocks         : {len(blocks)} found "
          f"({sum(b.action == 'run' for b in marked)} run, "
          f"{sum(b.action == 'skip' for b in marked)} skip)")
    for b in marked:
        if b.action == "skip":
            print(f"    - {b.label()} SKIPPED: {b.argument}")
    print()

    # Assertion 1
    check_block_outputs(root, config.get("expected", {}).get("dir", "docs/README.expected"), blocks, report)
    # Assertion 2
    check_symbols(blocks, import_names, report)
    # Assertion 6 -- the package -> README direction
    check_all_documented(
        readme,
        import_names,
        report,
        enabled=bool(pkg_cfg.get("require_all_documented", True)),
    )
    # Assertion 3
    tests_cfg = config.get("tests", {})
    check_test_count(
        root,
        readme,
        tests_cfg.get("path", "tests"),
        tests_cfg.get("claim_pattern", r"^(\d+)\s+tests\b"),
        report,
    )
    # Assertion 4
    deny_cfg = config.get("denylist", {})
    deny_file = root / deny_cfg.get("file", "docs-check-denylist.txt")
    if not deny_file.exists():
        sys.stderr.write(f"docs-check: no denylist file at {deny_file}\n")
        return 2
    check_denylist(
        root,
        load_denylist(deny_file),
        deny_cfg.get("targets", ["README.md", "pyproject.toml", "setup.py"]),
        report,
    )

    # ---- reconcile against the ledger --------------------------------
    ledger = load_ledger(config)
    ledger_by_id = {e.fid: e for e in ledger}
    actual_ids = set(report.ids)

    known_hit: List[Finding] = []
    real: List[Finding] = []
    for f in report.findings:
        (known_hit if f.fid in ledger_by_id else real).append(f)

    resolved = [e for e in ledger if e.fid not in actual_ids]

    print("-" * 72)
    for note in report.notes:
        print(f"  ok    {note}")

    if known_hit:
        print()
        print(f"  KNOWN FAILURES ({len(known_hit)}) -- tracked debt, not a pass:")
        for f in known_hit:
            e = ledger_by_id[f.fid]
            print(f"    [{f.fid}]")
            print(f"      {f.message}")
            print(f"      reason : {e.reason}")
            print(f"      owner  : {e.owner_release}")

    if resolved:
        print()
        print(f"  LEDGER ENTRIES THAT NOW PASS ({len(resolved)}) -- FAILURE:")
        for e in resolved:
            print(f"    [{e.fid}] no longer fails. Remove it from "
                  f"docs-check.toml [[known_failures]].")
            print(f"      (was: {e.reason}; owned by {e.owner_release})")

    if real:
        print()
        print(f"  FAILURES ({len(real)}):")
        for f in real:
            print(f"    [{f.fid}]")
            print(f"      {f.message}")

    print("-" * 72)
    if real or resolved:
        print(f"docs-check: FAIL "
              f"({len(real)} failure(s), {len(resolved)} stale ledger entr(y/ies), "
              f"{len(known_hit)} known)")
        return 1

    if known_hit:
        print(f"docs-check: PASS with {len(known_hit)} known failure(s) "
              f"-- see ledger above")
    else:
        print("docs-check: PASS (ledger empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
