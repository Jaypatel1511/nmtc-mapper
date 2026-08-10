"""Bundled methodology documents (ship inside the wheel AND the sdist).

A decision document that only exists in the repository is a document the
installed package cannot show you. These travel with the distribution and are
resolved through :func:`nmtcmapper.get_methodology_path`.

Shipping is not automatic and is not inherited: it needs
``[tool.setuptools.package-data]`` in pyproject.toml for the wheel and a
``recursive-include`` in MANIFEST.in for the sdist. hmda-analyzer nearly wrote
its methodology to a ``docs/`` path MANIFEST.in did not carry, which would have
shipped in neither artifact. ``tests/test_packaging.py`` asserts the file
resolves from the installed distribution so that cannot regress silently.
"""
from pathlib import Path

try:                                    # py3.9+ stdlib
    from importlib import resources
except ImportError:                     # pragma: no cover - unreachable on >=3.9
    import importlib_resources as resources  # type: ignore

DEFAULT_METHODOLOGY = "fabricated_negatives.md"


def get_methodology_path(filename: str = DEFAULT_METHODOLOGY) -> Path:
    """Return the filesystem path to a bundled methodology document.

    Args:
        filename: Name of the bundled doc. Defaults to the fabricated-negative
            methodology (what a ``False`` asserts in every boolean this package
            exposes, and why two fields get different remedies).

    Returns:
        A :class:`pathlib.Path` to the bundled file.

    Raises:
        FileNotFoundError: if no bundled file by that name exists.
    """
    ref = resources.files("nmtcmapper.methodology").joinpath(filename)
    if not ref.is_file():
        raise FileNotFoundError(
            f"bundled methodology file not found: {filename!r}"
        )
    return Path(str(ref))


__all__ = ["get_methodology_path", "DEFAULT_METHODOLOGY"]
