from nmtcmapper.mapper import NMTCMapper
from nmtcmapper.eligibility.checker import EligibilityResult
from nmtcmapper.data.loader import load_eligibility_table, load_sample_table
from nmtcmapper.geocoder.census import geocode_address
from nmtcmapper.exceptions import (
    NMTCMapperError,
    EligibilityDataError, EligibilityDownloadError, EligibilityParseError,
    EligibilitySchemaError, EligibilityValueError,
    OZDataError, OZDownloadError, OZParseError,
    GeocoderError, GeocoderTransportError, AmbiguousAddressError,
)

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("nmtc-mapper")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "NMTCMapper", "EligibilityResult",
    "load_eligibility_table", "load_sample_table", "geocode_address",
    "NMTCMapperError",
    "EligibilityDataError", "EligibilityDownloadError", "EligibilityParseError",
    "EligibilitySchemaError", "EligibilityValueError",
    "OZDataError", "OZDownloadError", "OZParseError",
    "GeocoderError", "GeocoderTransportError", "AmbiguousAddressError",
]
