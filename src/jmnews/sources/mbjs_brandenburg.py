"""MBJS Brandenburg — Ministerium für Bildung, Jugend und Sport.

Highly relevant for JM (Brandenburg-Trägeraufrufe, MBJS-Förderprogramme).
TYPO3-style press releases live under /aktuelles/pressemitteilungen.html
with query-string item URLs (?news=brandenburg_06.c.NNNNNN.de). The
listing page renders each entry as `<h2 class="news"><a>...</a></h2>`
followed by a teaser paragraph.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class MBJSBrandenburg(ScrapingSource):
    name = "mbjs_brandenburg"
    page_url = "https://mbjs.brandenburg.de/aktuelles/pressemitteilungen.html"
    base_url = "https://mbjs.brandenburg.de"
    selectors = ScrapeSelectors(
        # Each press release entry is a div wrapping h2.news + teaser; the
        # h2.news is a tighter pick than wrapper guessing.
        container="h2.news",
        title="a",
        link="a[href]",
        # Teaser is in the next sibling paragraph; selectolax can't traverse
        # easily, so we accept an empty snippet here.
        snippet="a",
        # No machine-readable date on the listing — falls back to now().
        date="time[datetime], time",
    )
