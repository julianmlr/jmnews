"""Berliner Zeitung RSS feed."""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class BerlinerZeitung(RSSSource):
    name = "berliner_zeitung"
    DEFAULT_URL = "https://www.berliner-zeitung.de/feed.xml"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def feed_urls(self) -> list[str]:
        return [self._url]
