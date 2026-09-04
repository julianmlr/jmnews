"""Brandenburg Vergabemarktplatz — public tenders by CPV category.

Two categories are polled, both named as indicators in the JM profile:

- CPV 85000000-9 "Health and social work services": the core feed
  (Jugendhilfe, Pflege, Migrationssozialarbeit, Unterbringung …).
- CPV 80000000-4 "Education and training services": adds tenders that never
  surface under CPV 85 — MBJS-Rahmenvereinbarungen, Grundbildung, schulische
  Präventions- und Jugendmaßnahmen der Landkreise, many of them published as
  "Beabsichtigte Ausschreibung", i.e. before the actual procurement starts.

The CPV label goes into the snippet so the downstream Claude filter can tell
a Bildungs- from a Sozialvergabe (see the profile rule for this source).

The portal is a Java/Struts app that returns ISO-8859-1 HTML; standard
ScrapingSource assumes UTF-8 so we handle the HTTP + decode ourselves.
"""

from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import HTTP_TIMEOUT, USER_AGENT, Source, parse_datetime

_OVERVIEW_URL = (
    "https://vergabemarktplatz.brandenburg.de/VMPCenter/company/"
    "announcements/categoryOverview.do?method=showTable&cpvCode={cpv}"
)

# (CPV code, short label for the snippet)
CPV_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("85000000-9", "CPV 85 Sozialwesen"),
    ("80000000-4", "CPV 80 Bildung"),
)


def build_category_url(cpv: str) -> str:
    return _OVERVIEW_URL.format(cpv=cpv)


class VergabeBrandenburg(Source):
    name = "vergabe_brandenburg"
    base_url = "https://vergabemarktplatz.brandenburg.de"
    request_delay = 2.0  # be polite between the two category requests

    def __init__(
        self, categories: tuple[tuple[str, str], ...] = CPV_CATEGORIES
    ) -> None:
        self._categories = categories

    def fetch(self, since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()
        for index, (cpv, label) in enumerate(self._categories):
            if index > 0 and self.request_delay > 0:
                time.sleep(self.request_delay)
            url = build_category_url(cpv)
            try:
                html = self._fetch_iso(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] HTTP fetch failed for {}: {}", self.name, cpv, exc)
                continue
            # A tender listed under both categories is kept once, under the
            # category that returned it first (CPV 85 wins).
            for item in self._parse(html, label):
                if item.id in seen:
                    continue
                seen.add(item.id)
                items.append(item)
        return [i for i in items if i.published_at >= since]

    def _fetch_iso(self, url: str) -> str:
        """The portal serves ISO-8859-1; httpx-default UTF-8 decode would corrupt umlauts."""
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.5"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content.decode("iso-8859-1")

    def _parse(self, html: str, cpv_label: str = "") -> list[NewsItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[NewsItem] = []
        seen: set[str] = set()
        tables = soup.select("table")
        if not tables:
            logger.info("[{}] no table found on page", self.name)
            return []

        for row in tables[0].select("tr"):
            cells = row.select("td")
            # 6 columns: published, deadline, title, type, vergabestelle, action-link
            if len(cells) < 6:
                continue
            published_text = cells[0].get_text(strip=True)
            deadline_text = cells[1].get_text(strip=True)
            title = cells[2].get_text(" ", strip=True)
            tender_type = cells[3].get_text(" ", strip=True)
            vergabestelle = cells[4].get_text(" ", strip=True)
            link_el = cells[5].select_one("a[href]")
            if not title or link_el is None:
                continue
            url = urljoin(self.base_url, link_el.get("href") or "")
            item_id = stable_id(url)
            if item_id in seen:
                continue
            seen.add(item_id)

            snippet_parts = [tender_type, vergabestelle]
            if deadline_text and deadline_text.lower() not in ("nv", "-", ""):
                snippet_parts.append(f"Frist: {deadline_text}")
            if cpv_label:
                snippet_parts.append(cpv_label)
            items.append(
                NewsItem(
                    id=item_id,
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=parse_datetime(published_text),
                    snippet=" | ".join(snippet_parts),
                )
            )
        return items
