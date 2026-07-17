"""
Typed exception hierarchy for nmtc-mapper (F1, added 0.3.4; extended 0.4.0).

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
    │  ├─ EligibilityParseError      # corrupt / wrong content-type / missing sheet / bad zip
    │  ├─ EligibilitySchemaError     # 0.4.0: column-count / header / row-count mismatch at load
    │  └─ EligibilityValueError      # 0.4.0: a parsed numeric value is out of plausible bounds
    ├─ OZDataError
    │  ├─ OZDownloadError
    │  └─ OZParseError
    └─ GeocoderError                 # 0.4.0: address -> tract resolution failures
       ├─ GeocoderTransportError     #   transport / HTTP-status / decode failure, retries exhausted
       └─ AmbiguousAddressError      #   multiple matches resolving to *different* tracts

Downstream code can catch at any level: `except NMTCMapperError` for anything,
`except EligibilityDataError` for eligibility-only, or a specific leaf.

C1 (0.4.0): EVERY class below subclasses NMTCMapperError. Nothing this package
raises may escape that tree — a downstream `except NMTCMapperError` must catch
all of it. tests/test_constraints.py enforces this by reflection.
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


class EligibilitySchemaError(EligibilityDataError):
    """The eligibility file was read, but its structure did not match the
    expected CDFI Fund layout (0.4.0).

    Raised at load time before any row is trusted: a wrong column count, a
    header string that does not match the live file at a positionally-bound
    index, or a degenerate/near-empty parse. The live loader binds columns
    POSITIONALLY, so an upstream column re-order would otherwise be read
    silently against the wrong fields. The message names the offending index,
    the expected value, and the actual value."""


class EligibilityValueError(EligibilityDataError):
    """A parsed numeric eligibility value fell outside its plausible bound (0.4.0).

    Guards against a silent upstream scale change — e.g. the AMI ratio column
    (stored as a FRACTION, ~0.91) flipping to percent-scale (~91.27), which
    would break every downstream AMI comparison by 100x while looking like
    ordinary data. The message names the field, the row index, and the value."""


class OZDataError(NMTCMapperError):
    """The Opportunity Zone designation dataset could not be obtained."""


class OZDownloadError(OZDataError):
    """Could not download the Opportunity Zone file (403 / 404 / DNS / timeout / connection),
    and no usable cached copy was available."""


class OZParseError(OZDataError):
    """The Opportunity Zone file was obtained but could not be parsed
    (corrupt bytes, wrong content-type, missing sheet / tract column, bad zip)."""


class GeocoderError(NMTCMapperError):
    """Address-to-census-tract resolution failed (0.4.0).

    Base for the geocoder failure modes that used to be collapsed into a single
    ``None`` return. ``None`` from the geocoder now means EXACTLY one thing —
    a genuine no-match (HTTP 200, zero address matches) — and every other
    failure raises a subclass of this."""


class GeocoderTransportError(GeocoderError):
    """The Census geocoder could not be reached or its response could not be
    read, after retries were exhausted (0.4.0).

    Covers HTTP status errors (403 / 5xx / …), timeouts, connection/DNS
    failures, and non-JSON/undecodable response bodies. The message names the
    failure kind and the address attempted so 403 vs 5xx vs timeout vs bad-JSON
    stay distinguishable — a typed error with the wrong story misdirects almost
    as badly as a silent one."""


class AmbiguousAddressError(GeocoderError):
    """The address matched multiple census tracts that do not agree (0.4.0).

    The geocoder returned more than one match and they resolve to DIFFERENT
    tracts, so there is no single correct answer. (If every match resolves to
    the SAME tract the ambiguity is harmless and no error is raised.) The
    message names the candidate tracts rather than silently taking the first."""


__all__ = [
    "NMTCMapperError",
    "EligibilityDataError",
    "EligibilityDownloadError",
    "EligibilityParseError",
    "EligibilitySchemaError",
    "EligibilityValueError",
    "OZDataError",
    "OZDownloadError",
    "OZParseError",
    "GeocoderError",
    "GeocoderTransportError",
    "AmbiguousAddressError",
]
