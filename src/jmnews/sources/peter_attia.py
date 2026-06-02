"""Peter Attia — longevity/healthspan blog and podcast show notes.

RSS feed at /feed/ delivers 2-3 substantial posts per week (AMAs, drive
podcast show notes, newsletter articles). Topics overlap directly with
JM's Tier-3 Background-Themen: sleep pharma, resistance training, Zone-2,
cancer screening, GH/peptides.

Output classification: always context (Hintergrund-Thema, never above per
profile discipline).
"""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class PeterAttia(RSSSource):
    name = "peter_attia"

    def feed_urls(self) -> list[str]:
        return ["https://peterattiamd.com/feed/"]
