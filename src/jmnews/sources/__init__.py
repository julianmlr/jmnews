"""Source registry. All 11 sources are enabled."""

from __future__ import annotations

from jmnews.sources.base import Source
from jmnews.sources.berlin_presseportal import BerlinPresseportal
from jmnews.sources.berliner_zeitung import BerlinerZeitung
from jmnews.sources.brandenburg_vorschriften import BrandenburgVorschriften
from jmnews.sources.bsfz import BSFZ
from jmnews.sources.daks import DaKS
from jmnews.sources.ibb import IBB
from jmnews.sources.ilb import ILB
from jmnews.sources.nbf import NbF
from jmnews.sources.rbb24 import Rbb24
from jmnews.sources.tagesspiegel import Tagesspiegel
from jmnews.sources.taz_berlin import TazBerlin


def enabled_sources() -> list[Source]:
    """All sources collected on each run.

    Returns:
        5 RSS sources + 6 HTML scrapers = 11 sources.
    """
    return [
        # RSS
        BerlinPresseportal(),
        Tagesspiegel(),
        BerlinerZeitung(),
        TazBerlin(),
        Rbb24(),
        # HTML scrapers
        IBB(),
        ILB(),
        BSFZ(),
        DaKS(),
        NbF(),
        BrandenburgVorschriften(),
    ]


__all__ = [
    "BSFZ",
    "IBB",
    "ILB",
    "BerlinPresseportal",
    "BerlinerZeitung",
    "BrandenburgVorschriften",
    "DaKS",
    "NbF",
    "Rbb24",
    "Source",
    "Tagesspiegel",
    "TazBerlin",
    "enabled_sources",
]
