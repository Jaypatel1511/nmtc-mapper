"""Typed exception hierarchy (F1) — importable from the package top level,
with the inheritance contract downstream catch-blocks will rely on."""
import pytest


def test_exceptions_importable_from_top_level():
    from nmtcmapper import (
        NMTCMapperError,
        EligibilityDataError, EligibilityDownloadError, EligibilityParseError,
        OZDataError, OZDownloadError, OZParseError,
    )
    assert issubclass(NMTCMapperError, Exception)


def test_eligibility_hierarchy():
    from nmtcmapper import (
        NMTCMapperError, EligibilityDataError,
        EligibilityDownloadError, EligibilityParseError,
    )
    assert issubclass(EligibilityDataError, NMTCMapperError)
    assert issubclass(EligibilityDownloadError, EligibilityDataError)
    assert issubclass(EligibilityParseError, EligibilityDataError)
    # download and parse are siblings, not each other
    assert not issubclass(EligibilityDownloadError, EligibilityParseError)


def test_oz_hierarchy():
    from nmtcmapper import (
        NMTCMapperError, OZDataError, OZDownloadError, OZParseError,
    )
    assert issubclass(OZDataError, NMTCMapperError)
    assert issubclass(OZDownloadError, OZDataError)
    assert issubclass(OZParseError, OZDataError)
    assert not issubclass(OZDownloadError, OZParseError)


def test_a_single_except_catches_every_data_error():
    """The whole point: one `except NMTCMapperError` catches all six leaves."""
    from nmtcmapper import (
        NMTCMapperError,
        EligibilityDownloadError, EligibilityParseError,
        OZDownloadError, OZParseError,
    )
    for exc in (EligibilityDownloadError, EligibilityParseError,
                OZDownloadError, OZParseError):
        with pytest.raises(NMTCMapperError):
            raise exc("boom")
