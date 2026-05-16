"""Source registry. Stage 7 only enables Berlin Presseportal as MVP source.

Stages 8+9 will add the remaining RSS and scraping sources.
"""

from __future__ import annotations

from jmnews.sources.base import Source
from jmnews.sources.berlin_presseportal import BerlinPresseportal


def enabled_sources() -> list[Source]:
    return [BerlinPresseportal()]


__all__ = ["Source", "enabled_sources"]
