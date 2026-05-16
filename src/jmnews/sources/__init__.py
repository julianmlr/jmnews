"""Source registry."""

from __future__ import annotations

from jmnews.sources.base import Source
from jmnews.sources.berlin_presseportal import BerlinPresseportal
from jmnews.sources.berliner_zeitung import BerlinerZeitung
from jmnews.sources.brandenburg_vorschriften import BrandenburgVorschriften
from jmnews.sources.bsfz import BSFZ
from jmnews.sources.daks import DaKS
from jmnews.sources.diakonie_bb import DiakonieBB
from jmnews.sources.dsee import DSEE
from jmnews.sources.ibb import IBB
from jmnews.sources.ilb import ILB
from jmnews.sources.nbf import NbF
from jmnews.sources.paritaet_berlin import ParitaetBerlin
from jmnews.sources.rbb24 import Rbb24
from jmnews.sources.tagesspiegel import Tagesspiegel
from jmnews.sources.taz_berlin import TazBerlin


def enabled_sources() -> list[Source]:
    """All sources collected on each run."""
    return [
        # RSS / feeds / sitemap
        BerlinPresseportal(),
        Tagesspiegel(),
        BerlinerZeitung(),
        TazBerlin(),
        Rbb24(),
        NbF(),
        DSEE(),
        # HTML scrapers
        IBB(),
        ILB(),
        BSFZ(),
        DaKS(),
        ParitaetBerlin(),
        DiakonieBB(),
        BrandenburgVorschriften(),
    ]


__all__ = [
    "BSFZ",
    "DSEE",
    "IBB",
    "ILB",
    "BerlinPresseportal",
    "BerlinerZeitung",
    "BrandenburgVorschriften",
    "DaKS",
    "DiakonieBB",
    "NbF",
    "ParitaetBerlin",
    "Rbb24",
    "Source",
    "Tagesspiegel",
    "TazBerlin",
    "enabled_sources",
]
