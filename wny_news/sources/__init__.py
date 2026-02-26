"""Source adapters for WNY news outlets."""

from sources.wgrz import WGRZAdapter
from sources.spectrum_buffalo import SpectrumBuffaloAdapter
from sources.city_of_buffalo import CityOfBuffaloAdapter
from sources.ub import UBAdapter
from sources.wkbw import WKBWAdapter
from sources.wgr550_audacy import WGR550Adapter
from sources.wivb import WIVBAdapter

ALL_ADAPTERS = [
    WGRZAdapter,
    SpectrumBuffaloAdapter,
    CityOfBuffaloAdapter,
    UBAdapter,
    WKBWAdapter,
    WGR550Adapter,
    WIVBAdapter,
]

__all__ = ["ALL_ADAPTERS"]
