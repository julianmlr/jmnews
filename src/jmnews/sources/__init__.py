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
from jmnews.sources.insolvenz import Insolvenz
from jmnews.sources.integras import Integras
from jmnews.sources.jugendhilfeportal import Jugendhilfeportal
from jmnews.sources.mbjs_brandenburg import MBJSBrandenburg
from jmnews.sources.nbf import NbF
from jmnews.sources.nexxt_change import NexxtChange
from jmnews.sources.paritaet_berlin import ParitaetBerlin
from jmnews.sources.rbb24 import Rbb24
from jmnews.sources.tagesspiegel import Tagesspiegel
from jmnews.sources.taz_berlin import TazBerlin
from jmnews.sources.vergabe_brandenburg import VergabeBrandenburg
from jmnews.sources.vpk import VPK


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
        MBJSBrandenburg(),
        Jugendhilfeportal(),
        VPK(),
        VergabeBrandenburg(),
        BrandenburgVorschriften(),
        Insolvenz(),
        NexxtChange(),
        Integras(),
    ]


__all__ = [
    "BSFZ",
    "DSEE",
    "IBB",
    "ILB",
    "Insolvenz",
    "Integras",
    "VPK",
    "BerlinPresseportal",
    "BerlinerZeitung",
    "BrandenburgVorschriften",
    "DaKS",
    "DiakonieBB",
    "Jugendhilfeportal",
    "MBJSBrandenburg",
    "NbF",
    "NexxtChange",
    "ParitaetBerlin",
    "Rbb24",
    "Source",
    "Tagesspiegel",
    "TazBerlin",
    "VergabeBrandenburg",
    "enabled_sources",
]
