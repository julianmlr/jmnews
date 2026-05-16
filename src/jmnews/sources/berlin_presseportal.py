"""Berlin Presseportal aggregated multi-institution RSS feed."""

from __future__ import annotations

from urllib.parse import quote_plus

from jmnews.sources.base import RSSSource

# Per spec: aggregated feed across these Berlin senate / district institutions.
DEFAULT_INSTITUTIONS: tuple[str, ...] = (
    "Senatsverwaltung für Bildung, Jugend und Familie",
    "Senatsverwaltung für Arbeit, Soziales, Gleichstellung, Integration, Vielfalt und Antidiskriminierung",  # noqa: E501
    "Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen",
    "Senatsverwaltung für Finanzen",
    "Senatsverwaltung für Wirtschaft, Energie und Betriebe",
    "Bezirksamt Treptow-Köpenick",
    "Bezirksamt Marzahn-Hellersdorf",
    "Bezirksamt Lichtenberg",
    "Bezirksamt Neukölln",
    "Bezirksamt Mitte",
)

BASE_URL = "https://www.berlin.de/presse/pressemitteilungen/index/feed"


def build_feed_url(institutions: tuple[str, ...] = DEFAULT_INSTITUTIONS) -> str:
    """Build the aggregated feed URL with multiple `institutions[]` params."""
    params = "&".join(f"institutions[]={quote_plus(i)}" for i in institutions)
    return f"{BASE_URL}?{params}"


class BerlinPresseportal(RSSSource):
    name = "berlin_presseportal"

    def __init__(self, institutions: tuple[str, ...] = DEFAULT_INSTITUTIONS) -> None:
        self._institutions = institutions

    def feed_urls(self) -> list[str]:
        return [build_feed_url(self._institutions)]
