"""IBB (Investitionsbank Berlin) news scraper.

Selectors are an initial guess — adjust on first VPS run if needed.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class IBB(ScrapingSource):
    name = "ibb"
    page_url = "https://www.ibb.de/de/ueber-die-ibb/aktuelles/aktuelles.html"
    base_url = "https://www.ibb.de"
    selectors = ScrapeSelectors(
        container="article, .news-item, .teaser",
        title="h2, h3, .headline",
        link="a[href]",
        snippet="p, .teaser-text",
        date="time[datetime], time, .date",
    )
