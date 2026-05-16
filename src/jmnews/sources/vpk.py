"""VPK Bundesverband — Aktuelles auf der Homepage.

VPK Brandenburg's own site (vpk-brandenburg.de) is unreliable; we use
the federal VPK site instead, which posts current statements, press
releases and Stellungnahmen relevant to private youth-welfare providers
across all German Bundesländer. Items appear as `div.text.col-sm-6`
boxes on the homepage; each box has an <h2> title, a <p> with date in
DD.MM.YYYY form, and an anchor to `/de/aktuelles/<slug>/`.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class VPK(ScrapingSource):
    name = "vpk"
    page_url = "https://www.vpk.de/de/"
    base_url = "https://www.vpk.de"
    selectors = ScrapeSelectors(
        container="div.text.col-sm-6",
        title="h2, h3",
        link='a[href*="/de/aktuelles/"]',
        # Snippet not separately exposed; falls back to title text.
        snippet="p",
        # Date is the first <p> with content "DD.MM.YYYY"; selectolax CSS
        # picks the first matching <p>, which on these cards is the date.
        date="p",
    )
