"""Bezirks-Jugendamt "Aktuelles" pages + SenBJF Ausschreibungen (berlin.de).

Some Trägeraufrufe never appear as Pressemitteilung: Bezirksjugendämter
post e.g. "Aufruf zur Angebotsabgabe" only on their Jugendamt-Aktuelles
page (standard berlin.de list module `ul.list--tablelist`), and SenBJF
publishes Ausschreibungs-PDFs in a download module on
/sen/bjf/service/ausschreibungen/. Neither page offers RSS.

The list pages carry no dates, so items fall back to now() on first
sight; storage dedupes by URL-derived id on later runs.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource

BASE_URL = "https://www.berlin.de"

# Standard berlin.de article-list module used by the Jugendamt pages.
_LIST_SELECTORS = ScrapeSelectors(
    container="ul.list--tablelist li",
    title="a",
    link="a[href]",
    snippet="p",
    date="time[datetime], time",
)

# Bezirke whose Jugendamt keeps a scrapeable Aktuelles list with content
# that is NOT mirrored as Pressemitteilung. URLs differ per Bezirk and
# 404 for most others — only add verified pages here. (Marzahn-Hellersdorf
# was checked and dropped: its Jugendamt page only embeds the general
# Bezirks-PM list, which the Presseportal feeds already cover.)
JUGENDAMT_PAGES: dict[str, str] = {
    "treptow_koepenick": (
        f"{BASE_URL}/ba-treptow-koepenick/politik-und-verwaltung/aemter/"
        "jugendamt/aktuelles/"
    ),
}


class JugendamtAktuelles(ScrapingSource):
    """One instance per Bezirk; parametrised over the Aktuelles URL."""

    base_url = BASE_URL
    selectors = _LIST_SELECTORS

    def __init__(self, bezirk: str, page_url: str) -> None:
        self.name = f"jugendamt_{bezirk}"
        self.page_url = page_url


def jugendamt_sources() -> list[JugendamtAktuelles]:
    return [JugendamtAktuelles(bezirk, url) for bezirk, url in JUGENDAMT_PAGES.items()]


class SenBJFAusschreibungen(ScrapingSource):
    """SenBJF Ausschreibungs-PDFs (download module, no dates)."""

    name = "senbjf_ausschreibungen"
    page_url = f"{BASE_URL}/sen/bjf/service/ausschreibungen/"
    base_url = BASE_URL
    selectors = ScrapeSelectors(
        container="li.modul-download",
        title="strong.title",
        link="a.link--download",
        snippet=".text p",
        date="time[datetime], time",
    )
