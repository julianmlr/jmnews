"""Source ABC and shared helpers for fetching news items."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from dateutil import parser as dateparser
from loguru import logger

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


def parse_datetime(value: Any) -> datetime:
    """Best-effort datetime parse with a `now(UTC)` fallback."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            dt = dateparser.parse(value)
            if dt is None:
                return datetime.now(UTC)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Failed to parse date {!r}, using now()", value)
    return datetime.now(UTC)


class RSSSource(Source):
    """Reusable RSS implementation. Subclasses provide `feed_urls()`."""

    @abstractmethod
    def feed_urls(self) -> list[str]:
        ...

    def fetch(self, since: datetime) -> list[NewsItem]:
        out: list[NewsItem] = []
        for url in self.feed_urls():
            try:
                raw = http_get(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] fetch failed for {}: {}", self.name, url, exc)
                continue
            out.extend(self._parse(raw))

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
