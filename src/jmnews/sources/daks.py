"""DaKS Berlin Marktplatz/Aktuelles scraper."""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class DaKS(ScrapingSource):
    name = "daks"
    page_url = "https://www.daks-berlin.de/"
    base_url = "https://www.daks-berlin.de"
    selectors = ScrapeSelectors(
        container="article, .news, .post, .teaser",
        title="h2, h3, .entry-title",
        link="a[href]",
        snippet="p, .entry-summary",
        date="time[datetime], time, .date, .entry-date",
    )
