"""Diakonie Berlin-Brandenburg-schlesische Oberlausitz — Aktuelles list.

Site is TYPO3; the /aktuelles/alle-meldungen page lists ~100 recent items
as `li.teaser-pagetile__element--contentful` cards with a date paragraph
and an h5 title inside .teaser-pagetile__content.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class DiakonieBB(ScrapingSource):
    name = "diakonie_bb"
    page_url = "https://www.diakonie-portal.de/aktuelles/alle-meldungen"
    base_url = "https://www.diakonie-portal.de"
    selectors = ScrapeSelectors(
        container="li.teaser-pagetile__element--contentful",
        title=".teaser-pagetile__text h5, h5",
        link='a[href*="/aktuelles/alle-meldungen/"]',
        snippet=".teaser-pagetile__text h5",
        date=".teaser-pagetile__date p, .teaser-pagetile__date",
    )
