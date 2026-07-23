"""Südkurier — regional daily for the Bodensee / Kreis Konstanz.

The Berlin outlets (rbb24, Tagesspiegel, taz) never cover the Bodensee region,
so this is JM's local-news channel for the Expansion Süd: Träger-/Heim-/Kita-
Meldungen, Jugendamts- and Kinderschutz-Themen around Konstanz.

Südkurier offers no per-region RSS (the region feed returns empty), so we
scrape the Kreis-Konstanz section page. It is a general local paper — most
teasers are traffic/sport/retail — so we keep only articles whose title/URL
match JM's social sector, mirroring how vergabe_berlin scopes itself. The
downstream Claude filter still scores the survivors.

Teasers carry the headline in the article's `aria-label` (cleaner than the
location-prefixed link text) and no reliable publish date on the listing, so
published_at falls back to now(); storage dedup by URL id prevents re-alerts.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import Source, http_get

# JM-relevant social-sector stems for the Bodensee expansion. Recall-oriented;
# the Claude filter does the final scoring.
_RELEVANCE_RE = re.compile(
    r"jugend|kita|kinder|erzieh|hort|wohngrupp|heim|jugendamt|tr(?:ä|ae)ger"
    r"|frauenhaus|gewaltschutz|pflege|sozial|betreuung|migration|fl(?:ü|ue)cht"
    r"|inobhut|hilfe zur erziehung|familienzentrum|kindergarten|krippe"
    r"|jugendhilfe|kinderschutz|schulsozial|sgb\s*viii|kvjs",
    re.IGNORECASE,
)


class Suedkurier(Source):
    name = "suedkurier"
    page_url = "https://www.suedkurier.de/region/kreis-konstanz/"
    base_url = "https://www.suedkurier.de"

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            html = http_get(self.page_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] HTTP fetch failed: {}", self.name, exc)
            return []
        items = self._parse(html)
        # No reliable listing dates → published_at is now(); the `since` gate is
        # a no-op here and storage dedup handles re-alerts.
        return [i for i in items if i.published_at >= since]

    def _parse(self, html: str) -> list[NewsItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[NewsItem] = []
        seen: set[str] = set()
        for art in soup.select("article[data-article-id]"):
            link = art.select_one("a[href*='/kreis-konstanz/']")
            if link is None or not link.get("href"):
                continue
            url = link["href"].split("?")[0]
            title = (art.get("aria-label") or link.get_text(" ", strip=True)).strip()
            if not title:
                continue
            if not _RELEVANCE_RE.search(f"{title} {url}"):
                continue
            item_id = stable_id(url)
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(
                NewsItem(
                    id=item_id,
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=datetime.now(UTC),
                    snippet="",
                )
            )
        return items
