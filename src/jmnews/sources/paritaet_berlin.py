"""Paritätischer Berlin — Aktuelles list (TYPO3).

The site has no public RSS; we scrape the /aktuelles list. Each entry is
an `article.c-teaser` with a link under `/aktuelles/detail/<slug>`. Dates
appear as plain text "DD.MM.YYYY" inside .c-meta__text and the title is
inside .c-teaser__heading-text.
"""

from __future__ import annotations

from jmnews.sources.base import ScrapeSelectors, ScrapingSource


class ParitaetBerlin(ScrapingSource):
    name = "paritaet_berlin"
    page_url = "https://www.paritaet-berlin.de/aktuelles"
    base_url = "https://www.paritaet-berlin.de"
    selectors = ScrapeSelectors(
        container="article.c-teaser",
        title=".c-teaser__heading-text, .c-teaser__heading a",
        link='a[href*="/aktuelles/detail/"]',
        snippet=".c-teaser__text p, .c-teaser__text",
        # The header has two .c-meta blocks: the first carries a topic tag,
        # the second carries Art + date. We need the LAST .c-meta__item of
        # the second list, which contains "DD.MM.YYYY".
        date=".c-meta__list.u-text-xs .c-meta__item:last-child .c-meta__text",
    )
