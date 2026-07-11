"""
Typed exception hierarchy for nmtc-mapper (F1, added 0.3.4).

Before 0.3.4 the loader silently substituted a synthetic sample dataset on ANY
download or parse failure, so a blocked network or a corrupt file produced a
*fabricated* eligibility answer with no signal to the caller. These exceptions
replace that behavior: every data-acquisition failure now raises, and the
message names the URL attempted and distinguishes access-blocked (403 /
connection / DNS) from not-found (404) from parse — so a caught error can never
be mistaken for a different problem (the HMDA 0.3.1 lesson: a typed error with a
misleading message misdirects just as badly as a swallowed one).

    NMTCMapperError
    ├─ EligibilityDataError
    │  ├─ EligibilityDownloadError   # 403 / 404 / DNS / timeout / connection
    │  └─ EligibilityParseError      # corrupt / wrong content-type / missing sheet / bad zip
    └─ OZDataError
       ├─ OZDownloadError
       └─ OZParseError

Downstream code can catch at any level: `except NMTCMapperError` for anything,
`except EligibilityDataError` for eligibility-only, or a specific leaf.
"""


class NMTCMapperError(Exception):
    """Base class for every error raised by nmtc-mapper."""


class EligibilityDataError(NMTCMapperError):
    """The CDFI Fund NMTC eligibility dataset could not be obtained."""


class EligibilityDownloadError(EligibilityDataError):
    """Could not download the eligibility file (403 / 404 / DNS / timeout / connection),
    and no usable cached copy was available."""


class EligibilityParseError(EligibilityDataError):
    """The eligibility file was obtained but could not be parsed
    (corrupt bytes, wrong content-type / HTML error page, missing sheet, bad zip)."""


class OZDataError(NMTCMapperError):
    """The Opportunity Zone designation dataset could not be obtained."""


class OZDownloadError(OZDataError):
    """Could not download the Opportunity Zone file (403 / 404 / DNS / timeout / connection),
    and no usable cached copy was available."""


class OZParseError(OZDataError):
    """The Opportunity Zone file was obtained but could not be parsed
    (corrupt bytes, wrong content-type, missing sheet / tract column, bad zip)."""


__all__ = [
    "NMTCMapperError",
    "EligibilityDataError",
    "EligibilityDownloadError",
    "EligibilityParseError",
    "OZDataError",
    "OZDownloadError",
    "OZParseError",
]
