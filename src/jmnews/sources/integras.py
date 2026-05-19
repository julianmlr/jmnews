"""INTEGRAS — Branchenverband CH-Heime / CEM (Comunità Educative).

The CH equivalent of LIGA / VPK for Sozial- und Sonderpädagogische
Einrichtungen. Posts on Trägerbewegungen, Fachtagungen, regulatorische
Entwicklungen in Schweizer Heim- und Jugendhilfe-Sektor. Highest signal
the public web offers for CH-M&A-relevant trends, since companymarket.ch
(commercial CH succession portal) is gated by Cloudflare bot management
that not even Playwright can clear.

Listing at /de/aktuelles with H3-wrapped article links to
/de/aktuelles/<slug>.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import Source, http_get

LISTING_URL = "https://integras.ch/de/aktuelles"


class Integras(Source):
    """CH branchen news: INTEGRAS Aktuelles."""

    name = "integras"

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            html = http_get(LISTING_URL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] fetch failed: {}", self.name, exc)
            return []
        soup = BeautifulSoup(html, "html.parser")
        items: list[NewsItem] = []
        seen: set[str] = set()
        # H2/H3 headlines wrapping an anchor to /de/aktuelles/<slug>
        for heading in soup.find_all(["h2", "h3", "h4"]):
            a = (
                heading.find("a", href=True)
                or heading.find_parent("a", href=True)
                or heading.find_next("a", href=True)
            )
            if a is None:
                continue
            href = a.get("href", "")
            if "/aktuelles/" not in href or href.rstrip("/").endswith("/aktuelles"):
                continue
            url = href if href.startswith("http") else f"https://integras.ch{href}"
            title = heading.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            items.append(
                NewsItem(
                    id=stable_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    # The listing has no machine-readable date — Sonnet will infer
                    # recency from the content. Set published_at = now so the
                    # 24h-lookback never drops fresh items.
                    published_at=datetime.now(UTC),
                    snippet="INTEGRAS Aktuelles (CH Heime / Sonderpädagogik)",
                )
            )
        return items
