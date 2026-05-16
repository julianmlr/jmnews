"""Source ABC and shared helpers for fetching news items."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from loguru import logger
from selectolax.parser import HTMLParser, Node

from jmnews.models import NewsItem, stable_id

USER_AGENT = "jmnews/0.1 (+https://github.com/julianmlr/jmnews)"
HTTP_TIMEOUT = 20.0


class Source(ABC):
    """Abstract base for any news source."""

    name: str = "unnamed"

    @abstractmethod
    def fetch(self, since: datetime) -> list[NewsItem]:
        """Return items published at or after `since`. Implementations must not raise."""


def http_get(url: str, *, timeout: float = HTTP_TIMEOUT) -> str:
    """Fetch URL with a configured User-Agent. Raises httpx exceptions on failure."""
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.5"},
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


# dateutil has no German locale; normalize month names before parsing.
_DE_MONTHS: dict[str, str] = {
    "Januar": "January", "Februar": "February", "März": "March", "Maerz": "March",
    "Mai": "May", "Juni": "June", "Juli": "July",
    "Oktober": "October", "Dezember": "December",
    # April, August, September, November are spelled the same in English.
}

# Last-resort fallback: pull a DD.MM.YYYY token out of a longer string
# like "Pressemitteilung vom 22.04.2026" that dateutil can't parse.
_DE_DATE_RE = re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b")


def _normalize_german_months(s: str) -> str:
    out = s
    for de, en in _DE_MONTHS.items():
        out = out.replace(de, en)
    return out


def parse_datetime(value: Any) -> datetime:
    """Best-effort datetime parse with a `now(UTC)` fallback.

    Uses `dayfirst=True` because all configured sources are German-language
    and dates appear in DD.MM.YYYY (or "5. Juni 2026") form; without this
    "12.05.2026" would be read as December 5th instead of May 12th.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        normalized = _normalize_german_months(value)
        try:
            dt = dateparser.parse(normalized, dayfirst=True)
            if dt is not None:
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            pass
        # dateutil failed on the full string — try extracting just a date token.
        match = _DE_DATE_RE.search(normalized)
        if match:
            try:
                dt = dateparser.parse(match.group(1), dayfirst=True)
                if dt is not None:
                    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                pass
        logger.warning("Failed to parse date {!r}, using now()", value)
    return datetime.now(UTC)


class RSSSource(Source):
    """Reusable RSS implementation. Subclasses provide `feed_urls()`."""

    @abstractmethod
    def feed_urls(self) -> list[str]:
        ...

    def fetch(self, since: datetime) -> list[NewsItem]:
        out: list[NewsItem] = []
        seen: set[str] = set()
        for url in self.feed_urls():
            try:
                raw = http_get(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] fetch failed for {}: {}", self.name, url, exc)
                continue
            for item in self._parse(raw):
                if item.id in seen:
                    continue
                seen.add(item.id)
                out.append(item)

        # Filter by `since` window.
        return [i for i in out if i.published_at >= since]

    def _parse(self, raw: str) -> list[NewsItem]:
        feed = feedparser.parse(raw)
        items: list[NewsItem] = []
        for entry in feed.entries:
            try:
                item = self._entry_to_item(entry)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[{}] skipping malformed entry: {}",
                    self.name,
                    exc,
                )
                continue
            if item is not None:
                items.append(item)
        return items

    def _entry_to_item(self, entry: Any) -> NewsItem | None:
        url = getattr(entry, "link", None) or entry.get("link")  # type: ignore[union-attr]
        if not url:
            return None
        title = getattr(entry, "title", None) or entry.get("title") or "(ohne Titel)"

        published_value: Any = (
            getattr(entry, "published", None)
            or getattr(entry, "updated", None)
            or entry.get("published")
            or entry.get("updated")
        )
        published_at = parse_datetime(published_value)

        summary = (
            getattr(entry, "summary", None)
            or getattr(entry, "description", None)
            or entry.get("summary", "")
        )
        snippet = strip_html(summary)

        return NewsItem(
            id=stable_id(url),
            source=self.name,
            title=title,
            url=url,
            published_at=published_at,
            snippet=snippet,
        )


# ---------------------------------------------------------------------------
# HTML scraping base
# ---------------------------------------------------------------------------


@dataclass
class ScrapeSelectors:
    """CSS selectors used by ScrapingSource to extract news items.

    Defaults match common patterns; override per site as needed.
    """

    container: str  # one selector match per article card
    title: str = "h2, h3, h4, .title, a"
    link: str = "a"
    snippet: str = "p, .summary, .excerpt"
    date: str = "time[datetime], time, .date, .pubdate"
    date_attr: str = "datetime"  # if matching element has this attr, prefer it
    excluded_titles: tuple[str, ...] = field(default_factory=tuple)


class ScrapingSource(Source):
    """Base for HTML scraping sources.

    Subclasses set name, page_url, base_url, and selectors. fetch() handles
    HTTP, parsing via selectolax with a BeautifulSoup fallback, and dataset
    filtering by `since`.
    """

    name: str = "unnamed_scraper"
    page_url: str = ""
    base_url: str = ""  # for resolving relative links; defaults to page_url origin
    selectors: ScrapeSelectors = ScrapeSelectors(container="article")

    def fetch(self, since: datetime) -> list[NewsItem]:
        if not self.page_url:
            logger.warning("[{}] no page_url configured", self.name)
            return []
        try:
            html = http_get(self.page_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] HTTP fetch failed: {}", self.name, exc)
            return []
        items = self._parse(html)
        return [i for i in items if i.published_at >= since]

    def _parse(self, html: str) -> list[NewsItem]:
        try:
            items = self._parse_selectolax(html)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] selectolax failed: {}; trying BS4", self.name, exc)
            items = []
        if not items:
            try:
                items = self._parse_bs4(html)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] BS4 parse failed: {}", self.name, exc)
                return []
        if not items:
            logger.info("[{}] no items found on page", self.name)
        return items

    def _parse_selectolax(self, html: str) -> list[NewsItem]:
        tree = HTMLParser(html)
        items: list[NewsItem] = []
        seen: set[str] = set()
        for node in tree.css(self.selectors.container):
            item = self._node_to_item(node)
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            items.append(item)
        return items

    def _node_to_item(self, node: Node) -> NewsItem | None:
        link_el = node.css_first(self.selectors.link)
        if link_el is None:
            return None
        href = link_el.attributes.get("href")
        if not href:
            return None
        url = urljoin(self.base_url or self.page_url, href)

        title_el = node.css_first(self.selectors.title)
        title = (title_el.text(strip=True) if title_el else link_el.text(strip=True)).strip()
        if not title:
            return None
        if title in self.selectors.excluded_titles:
            return None

        snippet_el = node.css_first(self.selectors.snippet)
        snippet = snippet_el.text(strip=True) if snippet_el else ""

        published_at = self._extract_date(node)

        return NewsItem(
            id=stable_id(url),
            source=self.name,
            title=title,
            url=url,
            published_at=published_at,
            snippet=snippet,
        )

    def _extract_date(self, node: Node) -> datetime:
        date_el = node.css_first(self.selectors.date)
        if date_el is None:
            return datetime.now(UTC)
        # Prefer the configured attribute (e.g. datetime="2026-05-16")
        attr_value = date_el.attributes.get(self.selectors.date_attr)
        if attr_value:
            return parse_datetime(attr_value)
        return parse_datetime(date_el.text(strip=True))

    def _parse_bs4(self, html: str) -> list[NewsItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[NewsItem] = []
        seen: set[str] = set()
        for container in soup.select(self.selectors.container):
            link = container.select_one(self.selectors.link)
            if not link or not link.get("href"):
                continue
            url = urljoin(self.base_url or self.page_url, link["href"])
            title_el = container.select_one(self.selectors.title) or link
            title = title_el.get_text(strip=True)
            if not title or title in self.selectors.excluded_titles:
                continue
            snippet_el = container.select_one(self.selectors.snippet)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            date_el = container.select_one(self.selectors.date)
            published_at = (
                parse_datetime(
                    date_el.get(self.selectors.date_attr) or date_el.get_text(strip=True)
                )
                if date_el
                else datetime.now(UTC)
            )
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
                    published_at=published_at,
                    snippet=snippet,
                )
            )
        return items
