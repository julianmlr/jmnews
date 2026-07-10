"""Source registry."""

from __future__ import annotations

from jmnews.sources.base import Source
from jmnews.sources.baulinks import Baulinks
from jmnews.sources.berlin_jugendaemter import (
    SenBJFAusschreibungen,
    jugendamt_sources,
)
from jmnews.sources.berlin_presseportal import BerlinPresseportal
from jmnews.sources.berlin_traegeraufrufe import BerlinTraegeraufrufe
from jmnews.sources.berliner_zeitung import BerlinerZeitung
from jmnews.sources.brandenburg_vorschriften import BrandenburgVorschriften
from jmnews.sources.bsfz import BSFZ
from jmnews.sources.creditreform import Creditreform
from jmnews.sources.daks import DaKS
from jmnews.sources.diakonie_bb import DiakonieBB
from jmnews.sources.dsee import DSEE
from jmnews.sources.eric_topol import EricTopol
from jmnews.sources.hdb_presse import HDBPresse
from jmnews.sources.ibb import IBB
from jmnews.sources.ilb import ILB
from jmnews.sources.insolvenz import Insolvenz
from jmnews.sources.integras import Integras
from jmnews.sources.jugendhilfeportal import Jugendhilfeportal
from jmnews.sources.lifespan_io import LifespanIo
from jmnews.sources.mbjs_brandenburg import MBJSBrandenburg
from jmnews.sources.nbf import NbF
from jmnews.sources.nexxt_change import NexxtChange
from jmnews.sources.paritaet_berlin import ParitaetBerlin
from jmnews.sources.peter_attia import PeterAttia
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
        BerlinTraegeraufrufe(),
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
        SenBJFAusschreibungen(),
        *jugendamt_sources(),
        BrandenburgVorschriften(),
        Insolvenz(),
        NexxtChange(),
        Integras(),
        # Longevity (Tier-3 Background-Themen)
        PeterAttia(),
        LifespanIo(),
        EricTopol(),
        # Bau-Software / Liquiditätstool competitive intelligence
        Baulinks(),
        HDBPresse(),
        Creditreform(),
    ]


__all__ = [
    "BSFZ",
    "DSEE",
    "IBB",
    "ILB",
    "Insolvenz",
    "Integras",
    "VPK",
    "Baulinks",
    "BerlinPresseportal",
    "BerlinTraegeraufrufe",
    "BerlinerZeitung",
    "BrandenburgVorschriften",
    "Creditreform",
    "DaKS",
    "DiakonieBB",
    "EricTopol",
    "HDBPresse",
    "Jugendhilfeportal",
    "LifespanIo",
    "MBJSBrandenburg",
    "NbF",
    "NexxtChange",
    "ParitaetBerlin",
    "PeterAttia",
    "Rbb24",
    "SenBJFAusschreibungen",
    "Source",
    "Tagesspiegel",
    "TazBerlin",
    "VergabeBrandenburg",
    "enabled_sources",
    "jugendamt_sources",
]
