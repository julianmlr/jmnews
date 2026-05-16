"""Jugendhilfeportal — Fachkräfteportal der Kinder- und Jugendhilfe.

Articles are exposed as `<a class="article-link-wrapper" href="/artikel/..."
title="...">`. The visible title lives in the anchor's `title` attribute,
not in inner text — the standard ScrapingSource extractor can't handle
that, so we use a custom fetch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urljoin

from loguru import logger
from selectolax.parser import HTMLParser

from jmnews.models import NewsItem, stable_id
from jmnews.sources import base
from jmnews.sources.base import Source


class Jugendhilfeportal(Source):
    name = "jugendhilfeportal"
    page_url = "https://www.jugendhilfeportal.de/"
    base_url = "https://www.jugendhilfeportal.de"

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            html = base.http_get(self.page_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] HTTP fetch failed: {}", self.name, exc)
            return []
        items = self._parse(html)
        return [i for i in items if i.published_at >= since]

    def _parse(self, html: str) -> list[NewsItem]:
        tree = HTMLParser(html)
        items: list[NewsItem] = []
        seen: set[str] = set()
        # No machine-readable date on the listing, so all items are stamped
        # "now"; the URL-hash dedup in storage ensures we don't double-insert
        # on later runs.
        now = datetime.now(UTC)
        for a in tree.css('a.article-link-wrapper'):
            href = a.attributes.get("href") or ""
            title = (a.attributes.get("title") or "").strip()
            if not href or not title:
                continue
            url = urljoin(self.base_url, href)
            item_id = stable_id(url)
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(
                NewsItem(
                    id=item_id,
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=now,
                    snippet="",
                )
            )
        return items
