"""Berlin Presseportal full-text feeds for Gewaltschutz / Frauenhaus topics.

Berlin is expanding its Frauenhaus / Frauen- und Kinderschutz capacity, and
the Träger-/Betreiberauswahl for these houses runs partly as
Interessenbekundungsverfahren announced by SenASGIVA and the Bezirke. Those
were slipping through: berlin_presseportal only covers a curated set of
institutions, and berlin_traegeraufrufe searches procurement-specific terms
(Trägeraufruf, IBV …) that a "Frauenhaus" announcement need not contain.

This source runs the same berlin.de ``?searchtext=`` feed against topic
terms so Frauenhaus/Gewaltschutz items surface regardless of which Amt
publishes them. Deliberately NOT listed among the Trägeraufruf-Alarm sources
(see briefing._TRAEGERAUFRUF_SOURCES): plain Frauenhaus *news* must not
trigger the alarm, while a Frauenhaus *tender* still does — its title/snippet
carries "Interessenbekundung"/"Trägeraufruf", which the alarm regex matches.

berlin.de rate-limits rapid feed hits ("429 Calm down"), hence request_delay.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from jmnews.sources.base import RSSSource

BASE_URL = "https://www.berlin.de/presse/pressemitteilungen/index/feed"

# One HTTP request per term (exact-word matching, no stemming), so both the
# umlaut compound and its parts are listed. Keep the list tight for rate limits.
SEARCH_TERMS: tuple[str, ...] = (
    "Frauenhaus",
    "Frauenhäuser",
    "Gewaltschutz",
    "Frauen- und Kinderschutzhaus",
    "Zufluchtswohnung",
)


def build_search_feed_url(term: str) -> str:
    """Feed URL for a full-text search across all berlin.de institutions."""
    return f"{BASE_URL}?searchtext={quote_plus(term)}"


class BerlinGewaltschutz(RSSSource):
    name = "berlin_gewaltschutz"
    request_delay = 3.0

    def __init__(self, search_terms: tuple[str, ...] = SEARCH_TERMS) -> None:
        self._terms = search_terms

    def feed_urls(self) -> list[str]:
        return [build_search_feed_url(term) for term in self._terms]
