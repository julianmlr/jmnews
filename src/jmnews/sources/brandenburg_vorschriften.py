"""Brandenburg Vorschriften (bravors) — recent regulations scraper."""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class BrandenburgVorschriften(ScrapingSource):
    name = "brandenburg_vorschriften"
    page_url = "https://bravors.brandenburg.de/"
    base_url = "https://bravors.brandenburg.de"
    selectors = ScrapeSelectors(
        container="article, .news, .vorschrift, li.result",
        title="h2, h3, a",
        link="a[href]",
        snippet="p",
        date="time[datetime], time, .date",
    )
