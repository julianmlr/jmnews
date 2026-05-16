"""Source registry. Stages 7-9 progressively enable more sources."""

from __future__ import annotations

from jmnews.sources.base import Source
from jmnews.sources.berlin_presseportal import BerlinPresseportal
from jmnews.sources.berliner_zeitung import BerlinerZeitung
from jmnews.sources.rbb24 import Rbb24
from jmnews.sources.tagesspiegel import Tagesspiegel
from jmnews.sources.taz_berlin import TazBerlin


def enabled_sources() -> list[Source]:
    """All sources collected on each run."""
    return [
        BerlinPresseportal(),
        Tagesspiegel(),
        BerlinerZeitung(),
        TazBerlin(),
        Rbb24(),
    ]


__all__ = [
    "BerlinPresseportal",
    "BerlinerZeitung",
    "Rbb24",
    "Source",
    "Tagesspiegel",
    "TazBerlin",
    "enabled_sources",
]
