#!/usr/bin/env bash
# repro-wheel-tests.sh -- reproduce release.yml's test-wheel job locally.
#
# THE PRE-TAG GATE THAT WAS MISSING. Release run #9 for 0.6.0 failed all eight
# test-wheel / test-sdist matrix jobs with `26 failed, 295 passed, 6 errors`
# while ci.yml, docs-check and every local run were green. ci.yml runs the
# suite FROM THE CHECKOUT, where docs/, tools/, CHANGELOG.md and the source
# tree exist; the release jobs run it from a directory holding ONLY
#
#     tests/  pyproject.toml  README.md
#
# with the package supplied by the installed wheel. That exclusion is the
# point of those jobs -- it is what makes them prove the artifact and not the
# checkout -- and it is an environment nothing before the tag reproduced. A
# gate that resolves `Path(__file__).resolve().parent.parent` and reaches for
# docs/ passes in one and fails in the other, and the first anyone learns of
# it is a failed release.
#
# RULE: ci.yml green is not a release gate when release.yml has jobs ci.yml
# does not. The only honest pre-tag check is to reproduce their layout. This
# script does exactly that, with test-wheel's exact pytest invocation, and it
# is a script rather than a runbook step because a procedure that lives only
# in a runbook is a procedure that gets skipped.
#
# The test-sdist job's run directory is the same three items (taken from the
# unpacked tarball rather than the checkout), so this layout stands for both;
# what test-sdist additionally proves -- that the tarball is complete -- is
# release.yml's job, not this script's.
#
# USAGE
#   scripts/repro-wheel-tests.sh                 build a wheel from this
#                                                checkout into a fresh venv,
#                                                then run the layout (~30s)
#   scripts/repro-wheel-tests.sh --python PY     skip the build: PY must
#                                                already import nmtcmapper
#                                                from site-packages and have
#                                                pytest (~2s)
#
# Expect it green. If it is red on a gate that reads docs/, tools/,
# CHANGELOG.md or nmtcmapper/*.py, the fix is to mark that gate `repo` and
# name it in tests/test_repo_marker.py -- NOT to copy the file in here, and
# not to copy it into release.yml either. See pyproject.toml's marker comment.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/repro-wheel-tests.XXXXXX")"
trap 'rm -rf "${WORK}"' EXIT

VPY=""
if [ "${1:-}" = "--python" ]; then
  VPY="${2:?--python needs an interpreter path}"
elif [ -n "${1:-}" ]; then
  echo "usage: $0 [--python PY]" >&2
  exit 2
fi

if [ -z "${VPY}" ]; then
  # Build from the checkout, exactly as release.yml's `build` job does, and
  # install into a venv that has never seen the source tree.
  echo "== building wheel from ${ROOT}"
  python3 -m venv "${WORK}/build-venv"
  "${WORK}/build-venv/bin/python" -m pip install --quiet --upgrade pip build
  ( cd "${ROOT}" && "${WORK}/build-venv/bin/python" -m build --wheel --outdir "${WORK}/dist" ) >/dev/null
  WHEEL="$(ls "${WORK}"/dist/*.whl)"
  echo "== installing ${WHEEL##*/} into a fresh venv"
  python3 -m venv "${WORK}/wheel-venv"
  VPY="${WORK}/wheel-venv/bin/python"
  "${VPY}" -m pip install --quiet --upgrade pip
  "${VPY}" -m pip install --quiet "${WHEEL}" pytest
fi

# test-wheel's run directory: tests/, pyproject.toml, README.md, and NOTHING
# else. No docs/, no tools/, no CHANGELOG.md, no nmtcmapper/.
TESTDIR="${WORK}/wheel-tests"
mkdir -p "${TESTDIR}"
cp -R "${ROOT}/tests" "${TESTDIR}/tests"
find "${TESTDIR}/tests" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "${ROOT}/pyproject.toml" "${TESTDIR}/pyproject.toml"
cp "${ROOT}/README.md" "${TESTDIR}/README.md"
cd "${TESTDIR}"
echo "== run directory: $(ls -m)"

# The same origin assertion as the job: if the import resolves anywhere but
# site-packages, this run is testing a source tree and proves nothing.
ORIGIN="$("${VPY}" -c 'import nmtcmapper; print(nmtcmapper.__file__)')"
echo "== import resolved to: ${ORIGIN}"
case "${ORIGIN}" in
  *"/site-packages/"*) ;;
  *) echo "ERROR: import nmtcmapper resolved to '${ORIGIN}', not an installed wheel" >&2
     echo "       (an editable install resolves to the checkout; use a venv with the wheel)" >&2
     exit 1 ;;
esac
echo "== installed __version__: $("${VPY}" -c 'import nmtcmapper; print(nmtcmapper.__version__)')"

# test-wheel's exact invocation (release.yml, job test-wheel, last line).
echo '== pytest tests -v --tb=short -m "not live and not repo" --import-mode=importlib --strict-markers'
"${VPY}" -m pytest tests -v --tb=short -m "not live and not repo" --import-mode=importlib --strict-markers
