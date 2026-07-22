"""Berlin Vergabeplattform — public tender announcements, social-sector filtered.

berlin.de/vergabeplattform publishes every Berlin public tender as an
``article.modul-card`` block on the Bekanntmachungen page. Unlike the
Brandenburg Vergabemarktplatz there is no CPV filter on the public page, so
we paginate (``?start=N``, 10 cards per page) and keep only tenders whose
title/snippet matches JM's social sector (Jugendhilfe, Kita, Frauenhaus,
Pflege …). The overwhelming majority of Berlin tenders are construction/IT
and irrelevant; the downstream Claude filter does the final scoring, this
pre-filter just keeps the feed (and token cost) sane, mirroring how
``vergabe_brandenburg`` scopes itself to CPV 85.

Each card's "Details" button links to the RIB e-procurement detail page; we
use that as the stable item URL (falling back to a constructed RIB URL from
the card's ``data-id`` if the button is missing).

berlin.de rate-limits rapid hits ("429 Calm down"), hence request_delay
between paginated requests.
"""

from __future__ import annotations

import re
import time
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import Source, http_get, parse_datetime

# Berlin's platformId on the RIB e-procurement backend (meinauftrag.rib.de).
_RIB_PLATFORM_ID = 2
_RIB_DETAIL = (
    "https://meinauftrag.rib.de/public/DetailsByPlatformIdAndTenderId/"
    "platformId/{platform}/tenderId/{tender}"
)

# JM-relevant social-sector stems. Substring match (case-insensitive) against
# title + snippet. Recall-oriented: the Claude filter scores the survivors, so
# a few false positives are cheaper than a missed Frauenhaus/Jugendhilfe tender.
_RELEVANCE_RE = re.compile(
    r"jugend|kita|kinder|erzieh|hort|sch(?:ü|ue)ler|wohngrupp|kinderheim"
    r"|betreu|pflege|sozial|migration|integration|fl(?:ü|ue)cht|asyl"
    r"|frauenhaus|gewaltschutz|frauen-?\s*und\s*kinderschutz|zuflucht"
    r"|beratung|eingliederung|teilhabe|behinder|obdach|wohnungslos"
    r"|unterbring|tr(?:ä|ae)ger|familie|senior|hilfe zur erziehung"
    r"|jugendhilfe|sgb\s*viii|heimerziehung|frühe hilfen|fruehe hilfen",
    re.IGNORECASE,
)

_ONLINE_SEIT_RE = re.compile(r"Online seit:\s*(\d{1,2}\.\d{1,2}\.\d{4})")


class VergabeBerlin(Source):
    name = "vergabe_berlin"
    base_url = "https://www.berlin.de"
    page_url = (
        "https://www.berlin.de/vergabeplattform/veroeffentlichungen/bekanntmachungen/"
    )
    # 10 cards per page; 6 pages = 60 newest tenders, plenty for a daily run.
    max_pages = 6
    request_delay = 3.0  # berlin.de answers rapid hits with "429 Calm down"

    def fetch(self, since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()
        for page in range(self.max_pages):
            if page > 0 and self.request_delay > 0:
                time.sleep(self.request_delay)
            start = page * 10
            url = self.page_url if start == 0 else f"{self.page_url}?start={start}"
            try:
                html = http_get(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] HTTP fetch failed at start={}: {}", self.name, start, exc)
                break
            card_count, page_items = self._parse(html)
            if card_count == 0:
                # No tender cards at all => past the end of the listing; stop.
                break
            new_ids = 0
            for item in page_items:
                if item.id in seen:
                    continue
                seen.add(item.id)
                new_ids += 1
                items.append(item)
            # Stop only when a full page of cards yields no *new* IDs (we've
            # looped back onto already-seen tenders). A page that simply has
            # no JM-relevant tenders is normal — keep paginating.
            if page_items and new_ids == 0:
                break
        return [i for i in items if i.published_at >= since]

    def _parse(self, html: str) -> tuple[int, list[NewsItem]]:
        """Return (raw card count, JM-relevant items).

        The card count drives pagination (0 => end of listing), independent of
        how many cards survive the social-sector relevance filter.
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("article.modul-card")
        items: list[NewsItem] = []
        for card in cards:
            title_el = card.select_one("h3.title, .title")
            if title_el is None:
                continue
            title = title_el.get_text(" ", strip=True)
            if not title:
                continue

            fields = self._card_fields(card)
            haystack = f"{title} {' '.join(fields.values())}"
            if not _RELEVANCE_RE.search(haystack):
                continue

            url = self._detail_url(card)
            if url is None:
                continue

            snippet_parts = [
                fields.get("Verfahrensart", ""),
                fields.get("Ausführungsort", ""),
            ]
            frist = fields.get("Ablauf Angebotsfrist", "")
            if frist:
                snippet_parts.append(f"Frist: {frist}")
            snippet = " | ".join(p for p in snippet_parts if p)

            items.append(
                NewsItem(
                    id=stable_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=self._published_at(card),
                    snippet=snippet,
                )
            )
        return len(cards), items

    @staticmethod
    def _card_fields(card) -> dict[str, str]:
        """Extract the dt/dd definition-list fields from a tender card."""
        dl = card.select_one("dl")
        if dl is None:
            return {}
        dts = dl.select("dt")
        dds = dl.select("dd")
        return {
            dt.get_text(" ", strip=True): dd.get_text(" ", strip=True)
            for dt, dd in zip(dts, dds, strict=False)
        }

    def _detail_url(self, card) -> str | None:
        el = card.select_one("[data-href]")
        href = el.get("data-href") if el else None
        if href:
            return href
        data_id = card.get("data-id")
        if data_id:
            return _RIB_DETAIL.format(platform=_RIB_PLATFORM_ID, tender=data_id)
        return None

    @staticmethod
    def _published_at(card) -> datetime:
        footer = card.select_one(".card__footer")
        if footer is not None:
            match = _ONLINE_SEIT_RE.search(footer.get_text(" ", strip=True))
            if match:
                return parse_datetime(match.group(1))
        return parse_datetime("")  # now(UTC) fallback
