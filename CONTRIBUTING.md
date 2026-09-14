# Contributing

Thank you for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Install dependencies:

    pip install -e .
    pip install pytest

4. Run the tests to confirm everything works:

    PYTHONPATH=. pytest tests/ -v

## Making Changes

1. Create a new branch:

    git checkout -b fix/your-fix-name

2. Make your changes
3. Add or update tests to cover your changes
4. Run the full test suite — all tests must pass
5. Commit with a clear message:

    git commit -m "fix: description of what you fixed"

6. Push and open a Pull Request against main

## Pull Request Guidelines

- Keep PRs focused — one fix or feature per PR
- All tests must pass before merging
- Add tests for any new functionality
- Update the README if you add new features or change the API
- Use clear, descriptive commit messages

## Releasing — the pre-tag checklist

`release.yml` runs on the tag and cannot be re-run before it. Everything below
is a gate the pipeline does **not** run, and each one is here because its
absence has already cost a release.

1. **Fetch every pinned external URL.** The four data files and the two
   geocoder endpoints this package depends on are third-party URLs with no
   version constraint and no notification when they move. CI deselects
   `@live`, so nothing but this step turns a moved file into a red test:

       PYTHONPATH=. pytest tests/test_live_pinned_urls.py -m live -v

   A failure names the constant and the page where the replacement is
   published. Re-pin; never downgrade (every earlier release pins the same
   literal). *0.6.1 exists because the CDFI Fund moved the eligibility file
   on 2026-09-03 and no gate fetched it.*

2. **Run the rest of the live suite** — the pinned headers, counts and
   digests against the real files:

       PYTHONPATH=. pytest tests -m live -v

   **If the CDFI Fund eligibility file is an `.xlsb` again**, this step is
   the only place real `.xlsb` bytes meet the pyxlsb path: the offline suite
   proves the container sniff on a synthetic zip and the row parse against a
   mock, and the one real `.xlsb` this package ever read is no longer
   downloadable (see `tests/test_workbook_dispatch.py`). Do not tag on the
   offline suite alone in that case.

3. **Run the offline suite** the way CI does:

       PYTHONPATH=. pytest tests -m "not live" -v

4. **Reproduce the packaged-layout jobs** (the check whose absence failed
   release run #9 for 0.6.0):

       scripts/repro-wheel-tests.sh

5. **Run the docs gate** against an installed wheel, the way `release.yml`'s
   docs-check job does — see the header of `tools/docs_check.py`.

6. **Re-read every deferred check** in the release notes and planning
   documents and ask whether its condition is *already* met. A "fragile if X
   ever happens" note is a claim about the present until someone has checked.

Then tag. Not before.

## Reporting Issues

Please open a GitHub Issue with:
- A clear description of the problem
- Steps to reproduce it
- Expected vs actual behavior
- Your Python version and OS

## Code Style

- Follow existing code style in the repo
- Use type hints where possible
- Add docstrings to public functions and classes
- Keep functions focused and single-purpose

## License

By contributing, you agree that your contributions will be licensed
under the MIT License.
