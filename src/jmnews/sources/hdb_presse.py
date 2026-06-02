"""Hauptverband der Deutschen Bauindustrie (HDB) — presseportal.de feed.

Official voice of the German construction industry: Baupreis-Index,
Konjunkturprognosen, "Tag der Bauindustrie" coverage, Bauwirtschafts-
politik. Provides the verbands-level macro context for JM's Liquiditäts-
tool sales narrative (when HDB warns about rising payment-delay days
or insolvency risks, that is a direct product-positioning signal).

Feed hosted on presseportal.de, standard RSS 2.0.
"""

from __future__ import annotations

from jmnews.sources.base import RSSSource


class HDBPresse(RSSSource):
    name = "hdb_presse"

    def feed_urls(self) -> list[str]:
        return ["https://www.presseportal.de/rss/pm_24058.rss2?langid=1"]
