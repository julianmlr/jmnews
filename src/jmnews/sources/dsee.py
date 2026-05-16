"""DSEE — Deutsche Stiftung für Engagement und Ehrenamt (WordPress feed).

Federal foundation that publishes funding programs and engagement-related
news. Their /aktuelles/ section is a regular WordPress blog with a feed.
"""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class DSEE(RSSSource):
    name = "dsee"
    DEFAULT_URL = "https://www.deutsche-stiftung-engagement-und-ehrenamt.de/feed/"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self._url = url

    def feed_urls(self) -> list[str]:
        return [self._url]
