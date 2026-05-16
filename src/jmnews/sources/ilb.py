"""ILB (Investitionsbank Brandenburg) news scraper."""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class ILB(ScrapingSource):
    name = "ilb"
    page_url = "https://www.ilb.de/de/aktuelles/"
    base_url = "https://www.ilb.de"
    selectors = ScrapeSelectors(
        container="article, .news-item, .teaser",
        title="h2, h3, .headline",
        link="a[href]",
        snippet="p, .teaser-text",
        date="time[datetime], time, .date",
    )
