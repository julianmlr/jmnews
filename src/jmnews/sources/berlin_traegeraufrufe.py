"""Berlin Presseportal full-text search feeds for Trägeraufrufe.

The institutions[] feeds in berlin_presseportal only cover a hand-picked
subset of Senatsverwaltungen and 6 of 12 Bezirke — but Trägeraufrufe /
Interessenbekundungsverfahren (IBV) are published by *any* Bezirksamt
(Steglitz-Zehlendorf, Charlottenburg-Wilmersdorf, Friedrichshain-Kreuzberg
were live examples in 2026) plus Landesbeauftragte and Senatsverwaltungen.

The same feed endpoint supports `?searchtext=<term>` full-text search
across ALL institutions, so one keyword feed per Trägeraufruf-typical
term catches every announcement regardless of which Amt publishes it.
Matching is exact-word (no stemming): "Interessenbekundung" does NOT
match "Interessenbekundungsverfahren", so both terms are needed.

berlin.de rate-limits rapid feed hits ("429 Calm down"), hence
request_delay between the keyword feeds.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from jmnews.sources.base import RSSSource

BASE_URL = "https://www.berlin.de/presse/pressemitteilungen/index/feed"

# One HTTP request per term; keep the list tight.
SEARCH_TERMS: tuple[str, ...] = (
    "Trägeraufruf",
    "Interessenbekundungsverfahren",
    "Interessenbekundung",
    "Förderaufruf",
    "Trägerauswahl",
)


def build_search_feed_url(term: str) -> str:
    """Feed URL for a full-text search across all berlin.de institutions."""
    return f"{BASE_URL}?searchtext={quote_plus(term)}"


class BerlinTraegeraufrufe(RSSSource):
    name = "berlin_traegeraufrufe"
    request_delay = 3.0

    def __init__(self, search_terms: tuple[str, ...] = SEARCH_TERMS) -> None:
        self._terms = search_terms

    def feed_urls(self) -> list[str]:
        return [build_search_feed_url(term) for term in self._terms]
