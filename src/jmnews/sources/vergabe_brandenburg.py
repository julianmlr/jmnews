"""Brandenburg Vergabemarktplatz — public tenders filtered by CPV 85.

CPV 85000000-9 covers "Health and social work services", i.e. directly
JM-relevant tenders (Jugendhilfe, Pflege, Migrationssozialarbeit etc.).

The portal is a Java/Struts app that returns ISO-8859-1 HTML; standard
ScrapingSource assumes UTF-8 so we handle the HTTP + decode ourselves.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import HTTP_TIMEOUT, USER_AGENT, Source, parse_datetime


class VergabeBrandenburg(Source):
    name = "vergabe_brandenburg"
    page_url = (
        "https://vergabemarktplatz.brandenburg.de/VMPCenter/company/"
        "announcements/categoryOverview.do?method=showTable&cpvCode=85000000-9"
    )
    base_url = "https://vergabemarktplatz.brandenburg.de"

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            html = self._fetch_iso()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] HTTP fetch failed: {}", self.name, exc)
            return []
        items = self._parse(html)
        return [i for i in items if i.published_at >= since]

    def _fetch_iso(self) -> str:
        """The portal serves ISO-8859-1; httpx-default UTF-8 decode would corrupt umlauts."""
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.5"},
        ) as client:
            resp = client.get(self.page_url)
            resp.raise_for_status()
            return resp.content.decode("iso-8859-1")

    def _parse(self, html: str) -> list[NewsItem]:
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
