"""taz Berlin RSS feed."""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class TazBerlin(RSSSource):
    name = "taz_berlin"
    DEFAULT_URL = "https://taz.de/!p4615;rss/"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def feed_urls(self) -> list[str]:
        return [self._url]
