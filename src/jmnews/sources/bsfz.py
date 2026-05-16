"""BSFZ Bescheinigungsstelle Forschungszulage news scraper."""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class BSFZ(ScrapingSource):
    name = "bsfz"
    page_url = "https://www.bescheinigung-forschungszulage.de/"
    base_url = "https://www.bescheinigung-forschungszulage.de"
    selectors = ScrapeSelectors(
        container="article, .news, .news-entry, .teaser",
        title="h2, h3, .headline",
        link="a[href]",
        snippet="p",
        date="time[datetime], time, .date",
    )
