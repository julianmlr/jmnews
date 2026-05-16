"""Berlin Presseportal aggregated multi-institution RSS feed."""

from __future__ import annotations

from urllib.parse import quote_plus

from jmnews.sources.base import RSSSource

# Aggregated feeds across Berlin senate / district / Landesamt institutions
# relevant for JM's profile (social, family, integration, health).
#
# berlin.de caps each feed at 10 items, so we split into thematic groups
# to avoid losing recent items while staying under the rate limit.
SENATE_INSTITUTIONS: tuple[str, ...] = (
    "Senatsverwaltung für Bildung, Jugend und Familie",
    "Senatsverwaltung für Arbeit, Soziales, Gleichstellung, Integration, Vielfalt und Antidiskriminierung",  # noqa: E501
    "Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen",
    "Senatsverwaltung für Finanzen",
    "Senatsverwaltung für Wirtschaft, Energie und Betriebe",
    "Senatsverwaltung für Wissenschaft, Gesundheit und Pflege",
    "Senatsverwaltung für Kultur und Gesellschaftlichen Zusammenhalt",
)
LANDESAEMTER_INSTITUTIONS: tuple[str, ...] = (
    "Beauftragte des Senats für Integration und Migration",
    "Landesamt für Gesundheit und Soziales",
    "Landesamt für Flüchtlingsangelegenheiten und Unterbringung",
    "Pflegebeauftragte des Landes Berlin",
)
BEZIRKE_INSTITUTIONS: tuple[str, ...] = (
    "Bezirksamt Treptow-Köpenick",
    "Bezirksamt Marzahn-Hellersdorf",
    "Bezirksamt Lichtenberg",
    "Bezirksamt Neukölln",
    "Bezirksamt Mitte",
)
DEFAULT_INSTITUTION_GROUPS: tuple[tuple[str, ...], ...] = (
    SENATE_INSTITUTIONS,
    LANDESAEMTER_INSTITUTIONS,
    BEZIRKE_INSTITUTIONS,
)
# Flat tuple of all configured institutions (preserves group order).
DEFAULT_INSTITUTIONS: tuple[str, ...] = tuple(
    inst for group in DEFAULT_INSTITUTION_GROUPS for inst in group
)

BASE_URL = "https://www.berlin.de/presse/pressemitteilungen/index/feed"


def build_feed_url(institutions: tuple[str, ...] = DEFAULT_INSTITUTIONS) -> str:
    """Build a feed URL with multiple `institutions[]` params."""
    params = "&".join(f"institutions[]={quote_plus(i)}" for i in institutions)
    return f"{BASE_URL}?{params}"


class BerlinPresseportal(RSSSource):
    name = "berlin_presseportal"

    def __init__(
        self,
        institution_groups: tuple[tuple[str, ...], ...] = DEFAULT_INSTITUTION_GROUPS,
    ) -> None:
        self._groups = institution_groups

    def feed_urls(self) -> list[str]:
        return [build_feed_url(group) for group in self._groups]
