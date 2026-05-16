"""DaKS Berlin Blog scraper (Drupal-based 'ganz frisch' news)."""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class DaKS(ScrapingSource):
    name = "daks"
    page_url = "https://www.daks-berlin.de/blog/ganz-frisch"
    base_url = "https://www.daks-berlin.de"
    selectors = ScrapeSelectors(
        container="article.node--type-blog",
        title="h2.node__title a, h2.node__title",
        link="h2.node__title a",
        snippet=".field--name-body p, .field--name-body",
        date="time[datetime], time, .field--name-created",
    )
