"""Creditreform — Bauinsolvenz / Zahlungsmoral signals.

Creditreform publishes monthly Mittelstandsreports, branchen-specific
insolvency stats and Zahlungsverzug-Studien. For JM's Liquiditäts-
tool venture this is the strongest *Bedarfssignal*-Quelle: rising
payment-delay days and Bau-Branche insolvency upticks directly justify
the product's positioning.

No RSS available — we scrape /aktuelles-wissen/pressemeldungen-
fachbeitraege which holds the 10 most recent news cards. URLs follow
the stable pattern /news-details/show/<slug>; the German publication
date sits at the start of each card snippet ("01. Juni 2026 ...") and
is parsed via the shared parse_datetime helper.

We do not pre-filter by Bau keywords here — the Haiku classification
step decides what is relevant. Creditreform's signal range (general
insolvency trend, mittelstand finance, Zahlungsmoral) is itself
narrow enough that everything reasonably feeds the broader product-
positioning context.
"""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import Source, http_get, parse_datetime, strip_html

LISTING_URL = (
    "https://www.creditreform.de/aktuelles-wissen/pressemeldungen-fachbeitraege"
)
BASE = "https://www.creditreform.de"

_DATE_PREFIX_RE = re.compile(
    r"^\s*(\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|"
    r"Juli|August|September|Oktober|November|Dezember)\s+\d{4})\s+(.*)$"
)


class Creditreform(Source):
    name = "creditreform"

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            html = http_get(LISTING_URL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] fetch failed: {}", self.name, exc)
            return []
        soup = BeautifulSoup(html, "html.parser")
        items: list[NewsItem] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news-details/show/" not in href:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 10:
                continue
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen:
                continue
            seen.add(url)

            parent = a.find_parent(["article", "div", "li"])
            published_at = datetime.now(UTC)
            snippet = ""
            if parent:
                ptext = strip_html(parent.get_text(" ", strip=True))
                cleaned = ptext.replace(title, "", 1).strip()
                m = _DATE_PREFIX_RE.match(cleaned)
                if m:
                    with contextlib.suppress(Exception):
                        published_at = parse_datetime(m.group(1))
                    snippet = m.group(2)[:300]
                else:
                    snippet = cleaned[:300]
            if published_at < since:
                continue
            items.append(
                NewsItem(
                    id=stable_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=published_at,
                    snippet=snippet,
                )
            )
        return items
