"""KVJS Baden-Württemberg — Landesjugendamt / Heimaufsicht news.

The Kommunalverband für Jugend und Soziales Baden-Württemberg runs the BW
Landesjugendamt: Betriebserlaubnis §45 SGB VIII, Aufsicht über stationäre
Jugendhilfe, Trägeranerkennung, KiTaG-Fragen. Its `/service/news` listing is
the public signal for regulatory movement in the Bodensee-region youth-welfare
market (JM's Expansion Süd).

Clean teaser markup — `div.news-list-item` with an `<h3>` title, a
`time[datetime]` stamp and a relative detail link — so the generic
ScrapingSource handles it directly. Volume is low and the base relevance is
high (it is the Landesjugendamt), so we do not keyword-filter here and let the
Claude profile filter score the items.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class KVJS(ScrapingSource):
    name = "kvjs"
    page_url = "https://www.kvjs.de/service/news"
    base_url = "https://www.kvjs.de"
    selectors = ScrapeSelectors(
        container="div.news-list-item",
        title="h3",
        link="a",
        snippet="p.text-content",
        date="time[datetime]",
        date_attr="datetime",
    )
