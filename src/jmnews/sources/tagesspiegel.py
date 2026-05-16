"""Tagesspiegel Berlin via Google-News-Sitemap.

Tagesspiegel exposes no RSS anymore; instead we parse the news sitemap
and filter for Berlin-section URLs (path starts with /berlin/).
"""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree as ET

from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources import base
from jmnews.sources.base import Source, parse_datetime

SITEMAP_NS = {
    "s": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "n": "http://www.google.com/schemas/sitemap-news/0.9",
}


class Tagesspiegel(Source):
    name = "tagesspiegel"
    DEFAULT_URL = "https://www.tagesspiegel.de/news.xml"
    BERLIN_PATH_PREFIX = "/berlin/"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            raw = base.http_get(self._url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] fetch failed for {}: {}", self.name, self._url, exc)
            return []
        try:
            return [i for i in self._parse(raw) if i.published_at >= since]
        except ET.ParseError as exc:
            logger.warning("[{}] sitemap parse failed: {}", self.name, exc)
            return []

    def _parse(self, raw: str) -> list[NewsItem]:
        root = ET.fromstring(raw)
        items: list[NewsItem] = []
        for url_el in root.findall("s:url", SITEMAP_NS):
            loc_el = url_el.find("s:loc", SITEMAP_NS)
            if loc_el is None or not loc_el.text:
                continue
            url = loc_el.text.strip()
            if self.BERLIN_PATH_PREFIX not in url:
                continue

            news_el = url_el.find("n:news", SITEMAP_NS)
            if news_el is None:
                continue
            title_el = news_el.find("n:title", SITEMAP_NS)
            date_el = news_el.find("n:publication_date", SITEMAP_NS)
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not title:
                continue
            published_at = parse_datetime(date_el.text if date_el is not None else None)

            items.append(
                NewsItem(
                    id=stable_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=published_at,
                    snippet="",
                )
            )
        return items
