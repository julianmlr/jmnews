"""Lifespan.io — longevity research journalism (rejuvenation, senolytics, trials).

High-frequency RSS (2-3 articles per day at peaks). Covers Rapamycin
research, senolytics trials, aging biotech funding, "Rejuvenation Roundup"
monthly digest. Highest signal for the Branchen-News dimension of
JM's Tier-3 Longevity interest.

Output classification: context only (background topic per profile rules).
"""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class LifespanIo(RSSSource):
    name = "lifespan_io"

    def feed_urls(self) -> list[str]:
        return ["https://www.lifespan.io/feed/"]
