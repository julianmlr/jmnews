"""Tagesspiegel Berlin RSS feed."""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class Tagesspiegel(RSSSource):
    name = "tagesspiegel"
    DEFAULT_URL = "https://www.tagesspiegel.de/contextmenu/rss/sections/berlin.xml"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def feed_urls(self) -> list[str]:
        return [self._url]
