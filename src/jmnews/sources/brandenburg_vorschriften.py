"""BRAVORS — Brandenburgisches Vorschriftensystem, newly issued regulations.

Covers the "Rechtsentwicklung" slice of JM's profile for Brandenburg: every
Gesetz, Verordnung and Verwaltungsvorschrift the Land issues — the MBJS
Richtlinien and Kita-/Jugendhilfe-Verordnungen among them.

This used to point `ScrapingSource` at `bravors.brandenburg.de/`, but that
root has never been a list: it redirects to the Schnellsuche *form*, so the
generic selectors matched nothing and the source logged "no items found on
page" every run since it was added. The site offers no chronological HTML
index either — `veroeffentlichungsblaetter_chronologisch` lists only gazette
PDFs, without publication dates.

What does work is the Erweiterte Suche: it takes an `ausfertigungsdatum_von`
bound and answers with the matching regulations **newest first**, each with
its own stable URL and issue date. So we ask it exactly the question the
pipeline is asking — "what was issued since `since`?" — and read the answer
off the result list.

Volume is low (single digits per month), so nothing is keyword-filtered here;
the Haiku classifier decides what is worth JM's attention.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup, Tag
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import HTTP_TIMEOUT, USER_AGENT, Source, parse_datetime

BASE = "https://bravors.brandenburg.de"
SEARCH_URL = f"{BASE}/de/vorschriften_erweiterte_suche"

# Results are 10 per page and date-descending, so a 72h window is served by
# page 1 alone. The cap only matters when someone widens the lookback a lot;
# we still stop early as soon as a result predates the window.
MAX_PAGES = 5

_VOM_RE = re.compile(r"vom\s+(\d{1,2}\.\d{1,2}\.\d{4})")


class BrandenburgVorschriften(Source):
    """Regulations issued in Brandenburg since the collection window start."""

    name = "brandenburg_vorschriften"

    def fetch(self, since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()
        try:
            with httpx.Client(
                timeout=HTTP_TIMEOUT,
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "de,en;q=0.5",
                },
            ) as client:
                # The search lives in the session: page 1 is the POST response,
                # every further page is a plain GET on the pager URL.
                response = client.post(SEARCH_URL, data=self._payload(since))
                response.raise_for_status()
                for page in range(1, MAX_PAGES + 1):
                    soup = BeautifulSoup(response.text, "html.parser")
                    page_items = list(self._parse(soup))
                    items.extend(i for i in page_items if i.id not in seen)
                    seen.update(i.id for i in page_items)
                    # Date-descending: once a result predates the window, so
                    # does everything after it.
                    if any(i.published_at < since for i in page_items):
                        break
                    next_url = self._next_page_url(soup, page + 1)
                    if next_url is None:
                        break
                    response = client.get(next_url)
                    response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[{}] search failed: {}", self.name, exc)
            return []
        return [i for i in items if i.published_at >= since]

    def _payload(self, since: datetime) -> dict[str, str]:
        """Advanced-search form values; only the issue-date bound is set."""
        return {
            "search[title]": "",
            "search[fulltext]": "",
            "search[art_vorschrift][]": "alle",
            "search[sachgebietsnr_1]": "",
            "search[gliederungsnr]": "",
            "search[ausfertigungsdatum_von]": since.strftime("%d.%m.%Y"),
            "search[ausfertigungsdatum_bis]": "",
            "search[inkrafttreten_von]": "",
            "search[inkrafttreten_bis]": "",
            "search[fundstelle_medium]": "0",
            "search[fundstelle_jahr]": "",
            "search[fundstelle_nr]": "",
            "search[fundstelle_seite]": "",
            "suchen": "Suchen",
        }

    def _parse(self, soup: BeautifulSoup) -> list[NewsItem]:
        result_list = soup.select_one(".ergebnisliste dl")
        if result_list is None:
            return []
        out: list[NewsItem] = []
        for entry in result_list.find_all("dt", recursive=False):
            item = self._entry_to_item(entry)
            if item is not None:
                out.append(item)
        return out

    def _entry_to_item(self, entry: Tag) -> NewsItem | None:
        link = entry.select_one(".link a[href]")
        if link is None:
            return None
        title = link.get_text(" ", strip=True)
        if not title:
            return None

        # The date and the Sachgebiet follow the <dt> as sibling <dd>s.
        datum = ""
        sachgebiet = ""
        sibling = entry.find_next_sibling()
        while isinstance(sibling, Tag) and sibling.name == "dd":
            classes: list[str] = list(sibling.get("class") or [])
            if "datum" in classes:
                datum = sibling.get_text(" ", strip=True)
            elif "gl_nr" in classes:
                sachgebiet = " ".join(sibling.get_text(" ", strip=True).split())
            sibling = sibling.find_next_sibling()
        if not datum:
            return None

        # "vom 06.08.2026" — hand parse_datetime the bare date so a German
        # prefix can never push it onto the now() fallback.
        match = _VOM_RE.search(datum)
        published = parse_datetime(match.group(1) if match else datum)

        href = str(link["href"])
        url = f"{BASE}{href}" if href.startswith("/") else href
        return NewsItem(
            id=stable_id(url),
            source=self.name,
            title=title,
            url=url,
            published_at=published,
            snippet=sachgebiet or "Brandenburgische Vorschrift",
        )

    def _next_page_url(self, soup: BeautifulSoup, page: int) -> str | None:
        header = soup.select_one(".ergebnisliste_kopf")
        if header is None:
            return None
        for link in header.find_all("a", href=True):
            if link.get_text(strip=True) == str(page):
                href = str(link["href"])
                return f"{BASE}{href}" if href.startswith("/") else href
        return None
