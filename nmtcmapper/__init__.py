from nmtcmapper.mapper import NMTCMapper
from nmtcmapper.eligibility.checker import EligibilityResult
from nmtcmapper.data.loader import load_eligibility_table
from nmtcmapper.geocoder.census import geocode_address

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("nmtc-mapper")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "NMTCMapper", "EligibilityResult",
    "load_eligibility_table", "geocode_address",
]
