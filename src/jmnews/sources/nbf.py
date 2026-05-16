"""NbF Brandenburg WordPress RSS feed."""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class NbF(RSSSource):
    name = "nbf"
    DEFAULT_URL = "https://www.nbfev.de/feed/"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def feed_urls(self) -> list[str]:
        return [self._url]
