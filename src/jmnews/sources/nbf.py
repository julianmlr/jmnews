"""NbF Brandenburg news scraper."""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class NbF(ScrapingSource):
    name = "nbf"
    page_url = "https://www.nbfev.de/"
    base_url = "https://www.nbfev.de"
    selectors = ScrapeSelectors(
        container="article, .news, .post, .teaser",
        title="h2, h3, .entry-title",
        link="a[href]",
        snippet="p, .entry-summary",
        date="time[datetime], time, .date",
    )
