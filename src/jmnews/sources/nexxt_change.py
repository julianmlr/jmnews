"""nexxt-change.org — official KfW/BAFA business succession marketplace.

Polls two NACE branches relevant to JM:
- [5,63] Sozialwesen (ohne Heime) — Kita-Verkäufe, ambulante Jugendhilfe etc.
- [5,27] Heime — usually Pflege/Senioren, but the occasional Kinderheim
  ends up here; client-side keyword filter weeds out the senior-care noise.

The search uses a POST form with CSRF tokens (resourceId, input_,
__time_token) extracted from a GET on the form page. Result cards live
in `.inserat-list-item` with stable per-offer URLs of the form
`detailseite_jsp?adId=NNNNNN`.

Volume is low in the social-sector branches (single digits at any time)
so we hit the endpoint sparingly and only escalate when keywords match.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import HTTP_TIMEOUT, USER_AGENT, Source, parse_datetime

SEARCH_URL = (
    "https://www.nexxt-change.org/SiteGlobals/Forms/"
    "Verkaufsangebot_Suche/Verkaufsangebotssuche_Formular"
)
NACE_FILTERS = (
    ("[5,63]", "Sozialwesen ohne Heime"),
    ("[5,27]", "Heime"),
)

# Pflege/Senioren-Inserate aus NACE [5,27] sind irrelevant — wir wollen
# nur Kinderheime, Jugendhilfe-Einrichtungen, Kitas.
_RELEVANT_TOKENS = re.compile(
    r"\b("
    r"kita|kindertag|kindergarten|krippe|hort|"
    r"kinderhaus|kinderheim|jugendhilfe|jugendwohn|"
    r"erziehung|familienzentrum|tagespflege|"
    r"bildungseinrichtung|grundschule"
    r")\b",
    re.IGNORECASE,
)
_PFLEGE_NOISE = re.compile(
    r"\b(seniorenheim|pflegeheim|pflegeeinrichtung|altenheim|"
    r"betreutes\s+wohnen|alkoholiker)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")


class NexxtChange(Source):
    """KfW/BAFA Nachfolgebörse — filtered for Kita/Jugendhilfe."""

    name = "nexxt_change"

    def fetch(self, since: datetime) -> list[NewsItem]:
        items_by_id: dict[str, NewsItem] = {}
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "de,en;q=0.5",
            },
        ) as client:
            for nace, label in NACE_FILTERS:
                try:
                    rows = self._search(client, nace)
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "[{}] search for NACE {} ({}) failed: {}",
                        self.name, nace, label, exc,
                    )
                    continue
                for item in self._rows_to_items(rows, nace_label=label):
                    if item.published_at < since:
                        continue
                    items_by_id.setdefault(item.id, item)
        return list(items_by_id.values())

    def _search(self, client: httpx.Client, nace: str) -> list[BeautifulSoup]:
        r = client.get(SEARCH_URL + ".html")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form", action=lambda a: a and "Verkaufs" in a)
        if form is None:
            raise ValueError("Search form not found")
        rid = form.find("input", {"name": "resourceId"})
        inp = form.find("input", {"name": "input_"})
        tok = form.find("input", {"name": "__time_token"})
        if not (rid and inp and tok):
            raise ValueError("CSRF tokens missing")
        payload = {
            "resourceId": rid["value"],
            "input_": inp["value"],
            "pageLocale": "de",
            "__time_token": tok["value"],
            "suchbegriff": "",
            "ad_fuzzysearch": "1",
            "ad_nace": nace,
            "ad_nace.GROUP": "1",
            "ad_nuts": "",
            "ad_nuts.GROUP": "1",
            "ad_zip": "",
            "ad_radius": "15",
            "excludeSuchbegriff": "",
            "ad_sizeturnover": "",
            "ad_sizeturnover.GROUP": "1",
            "ad_sizestaff": "",
            "ad_sizestaff.GROUP": "1",
            "ad_pricerange": "",
            "ad_pricerange.GROUP": "1",
            "ad_internationalactivity": "",
            "ad_internationalactivity.GROUP": "1",
            "ad_onlyWithExpose.GROUP": "1",
            "ad_onlyWithImages.GROUP": "1",
            "ad_advertisergroup": "1",
            "ad_advertisergroup.GROUP": "1",
            "ad_association": "",
            "ad_association.GROUP": "1",
            "rp_id": "",
        }
        r2 = client.post(SEARCH_URL, data=payload)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "html.parser")
        return soup2.select(".inserat-list-item")

    def _rows_to_items(
        self,
        rows: Iterable[BeautifulSoup],
        *,
        nace_label: str,
    ) -> list[NewsItem]:
        out: list[NewsItem] = []
        for row in rows:
            a = row.find("a", href=True)
            if a is None:
                continue
            url = a["href"]
            if not url.startswith("http"):
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                heading = row.find(["h2", "h3", "h4", "strong"])
                title = heading.get_text(" ", strip=True) if heading else ""
            if not title:
                continue
            full_text = row.get_text(" ", strip=True)
            # NACE [5,27] (Heime) is dominated by Pflege — keep only items
            # that match a Kita/Jugendhilfe token. NACE [5,63] (Sozialwesen)
            # is narrow enough that we keep everything except explicit
            # Pflege/Senioren noise.
            if (
                ("27" in nace_label.lower() or "heime" in nace_label.lower())
                and not _RELEVANT_TOKENS.search(full_text)
            ):
                continue
            if _PFLEGE_NOISE.search(full_text) and not _RELEVANT_TOKENS.search(full_text):
                continue

            m = _DATE_RE.search(full_text)
            if m:
                try:
                    published = parse_datetime(m.group(1))
                except Exception:  # noqa: BLE001
                    published = datetime.now(tz=__import__("datetime").UTC)
            else:
                published = datetime.now(tz=__import__("datetime").UTC)

            out.append(
                NewsItem(
                    id=stable_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=published,
                    snippet=f"Verkaufsangebot — {nace_label}",
                )
            )
        return out
