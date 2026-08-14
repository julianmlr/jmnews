"""SenBJF Aufsicht Berlin — Heimaufsicht (§45 SGB VIII) und Kitaaufsicht.

Die Berliner Aufsichtsbehörde publiziert ihre Vorgaben NICHT über Presse-
mitteilungen (searchtext-Feeds auf "Betriebserlaubnis"/"Heimaufsicht"/
"Einrichtungsaufsicht" liefern durchgehend 0 Treffer) — aufsichtsrechtliche
Fachinformationen erscheinen ausschließlich als Download-Module auf den
Fachinfo-Seiten der Senatsverwaltung. Diese Quelle scraped genau die:

- Einrichtungsaufsicht (= Heimaufsicht für stationäre Jugendhilfe, §45 SGB
  VIII): Infoblatt Neugründung, Meldung besonderer Vorkommnisse, Raum- und
  Ausstattungsstandards, Kinderrechte/Beschwerdemanagement.
- Kitaaufsicht: Trägerrundschreiben, Fachkräfteregelung, Quereinstieg.

Beides ist für JM direkt relevant (Sophien Hof gGmbH = Heim in Gründung,
Kita Sophiechen = laufender Betrieb): Änderungen an Standards oder Melde-
pflichten schlagen unmittelbar auf Betriebserlaubnis und Betrieb durch.

Identität/Versionierung: Die PDF-Links tragen einen `?ts=`-Cache-Buster
(Datei-mtime). Der taugt NICHT als Versionsmerkmal — mehrere Dokumente
teilen denselben ts aus einer CMS-Massenmigration, was einen Schwall
falscher "neu"-Meldungen auslösen würde. Stattdessen bildet das redaktionell
gepflegte "Stand: <Monat Jahr>" aus der Caption die Version: die Item-ID ist
(bereinigte URL + Stand), sodass eine inhaltlich neu gefasste Fachinfo genau
einmal neu meldet, eine bloße Neu-Verlinkung dagegen nicht.

Wie senbjf_ausschreibungen tragen die Download-Module kein Veröffentlichungs-
datum; published_at fällt auf now() zurück, Dedup läuft über die Item-ID.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import Source, http_get

BASE_URL = "https://www.berlin.de"
_AUFSICHT_ROOT = f"{BASE_URL}/sen/jugend/familie-und-kinder/aufsicht"

# label → Fachinfo-Seite. Das Label landet im Snippet, damit im Briefing
# sofort erkennbar ist, ob es die Heim- oder die Kita-Aufsicht betrifft.
AUFSICHT_PAGES: tuple[tuple[str, str], ...] = (
    ("Heimaufsicht (Einrichtungsaufsicht §45 SGB VIII)",
     f"{_AUFSICHT_ROOT}/einrichtungsaufsicht-fachinfo/"),
    ("Kitaaufsicht", f"{_AUFSICHT_ROOT}/kitaaufsicht/fachinfo/"),
)

_STAND_RE = re.compile(r"Stand:\s*([^|)\n]+)", re.IGNORECASE)


class BerlinAufsicht(Source):
    name = "berlin_aufsicht"
    request_delay = 3.0  # berlin.de answers rapid hits with "429 Calm down"

    def __init__(self, pages: tuple[tuple[str, str], ...] = AUFSICHT_PAGES) -> None:
        self._pages = pages

    def fetch(self, since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()
        for index, (label, url) in enumerate(self._pages):
            if index > 0 and self.request_delay > 0:
                time.sleep(self.request_delay)
            try:
                html = http_get(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] fetch failed for {}: {}", self.name, url, exc)
                continue
            for item in self._parse(html, label):
                if item.id in seen:
                    continue
                seen.add(item.id)
                items.append(item)
        return [i for i in items if i.published_at >= since]

    def _parse(self, html: str, label: str) -> list[NewsItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[NewsItem] = []
        for module in soup.select("li.modul-download"):
            title_el = module.select_one("strong.title, .title")
            link_el = module.select_one("a.link--download, a[href]")
            if title_el is None or link_el is None or not link_el.get("href"):
                continue
            title = title_el.get_text(" ", strip=True)
            if not title:
                continue

            # Strip the `?ts=` cache-buster so the URL stays canonical.
            href = link_el["href"].split("?")[0]
            url = urljoin(BASE_URL, href)

            caption = module.select_one("p.caption")
            caption_text = caption.get_text(" ", strip=True) if caption else ""
            stand_match = _STAND_RE.search(caption_text)
            stand = stand_match.group(1).strip() if stand_match else ""

            snippet_parts = [label]
            if stand:
                snippet_parts.append(f"Stand: {stand}")
            doc_type = module.select_one(".doc-type")
            if doc_type is not None:
                snippet_parts.append(doc_type.get_text(" ", strip=True))

            items.append(
                NewsItem(
                    # Version = redaktioneller "Stand", nicht der ts-Cachebuster.
                    id=stable_id(f"{url}|{stand}"),
                    source=self.name,
                    title=title,
                    url=url,
                    published_at=datetime.now(UTC),
                    snippet=" | ".join(snippet_parts),
                )
            )
        return items
