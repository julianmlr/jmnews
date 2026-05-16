"""rbb24 RSS feed (Berlin-Brandenburg public broadcaster)."""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class Rbb24(RSSSource):
    name = "rbb24"
    DEFAULT_URL = "https://www.rbb24.de/index.feed"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def feed_urls(self) -> list[str]:
        return [self._url]
