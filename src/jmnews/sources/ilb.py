"""ILB (Investitionsbank Brandenburg) — Meldungen zu den Förderprogrammen.

Die ILB hat ihren Webauftritt auf ein Headless-CMS (e-spirit CaaS) hinter
einer Nuxt-SPA umgestellt. Damit ist die alte Quelle gestorben: `/de/aktuelles/`
liefert 404 (ebenso `/de/presse/` und `/de/newsroom/`), die ausgelieferten
Seiten enthalten kein einziges `article`/`time`-Element — alles wird client-
seitig gerendert — und die Content-API (`ilb-caas-api.e-spirit.cloud`)
antwortet ohne Token mit 401. Ein CSS-Scraper kann dort nichts mehr finden.

Was die Seite aber ausliefert, ist das vollständige Nuxt-Payload im
`__NUXT_DATA__`-Script. Darin stehen die redaktionellen Programm-Meldungen
der ILB als eigene Objekte, mit Überschrift, Kurztext und `datum` — genau
die Ereignisse, die JM interessieren: "1. Richtlinienänderung", "Start der
Antragstellung", "Call verlängert", "Neues Merkblatt online".

Beobachtet werden die drei Programmübersichten mit Trägerbezug:
Arbeit (ESF, Fachkräfte, Projekte Schule/Jugendhilfe, Sozialbetriebe),
Infrastruktur (Investitionsprogramm Ganztag, Startchancen, Schulbau) und
Wohnungsbau (soziale Wohnraumförderung).

Bewusst NICHT umgesetzt: ein Inventar-Diff über alle ~300 Programmobjekte je
Seite. Der wäre statuslos nur über die Item-ID abbildbar und würde beim ersten
Lauf mehrere hundert Einträge ins Briefing kippen — die Meldungen tragen ein
echtes `datum` und filtern sich sauber über das Sammelfenster.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import USER_AGENT, Source, parse_datetime

BASE_URL = "https://www.ilb.de"

# label → Programmübersicht. Das Label landet im Snippet, damit im Briefing
# erkennbar ist, aus welchem Förderbereich die Meldung stammt.
PROGRAMME_PAGES: tuple[tuple[str, str], ...] = (
    ("Arbeit", f"{BASE_URL}/de/arbeit/uebersicht-der-foerderprogramme/"),
    ("Infrastruktur", f"{BASE_URL}/de/infrastruktur/alle-infrastruktur-foerderprogramme/"),
    ("Wohnungsbau", f"{BASE_URL}/de/wohnungsbau/uebersicht-der-foerderprogramme/"),
)

# Die Payloads sind 1-2,5 MB groß; der Default-Timeout von 20s ist dafür knapp.
PAGE_TIMEOUT = 45.0

_NUXT_RE = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# Pflichtfelder eines Meldungsobjekts. Die Kombination ist im Payload
# eindeutig — Programm- und Navigationsobjekte tragen kein `ueberschrift`.
_NEWS_KEYS = frozenset({"ueberschrift", "datum", "kurztext", "bezeichnung"})

_MAX_DEPTH = 8


class ILB(Source):
    """Programm-Meldungen der ILB aus dem Nuxt-Payload."""

    name = "ilb"

    def __init__(self, pages: tuple[tuple[str, str], ...] = PROGRAMME_PAGES) -> None:
        self._pages = pages

    def fetch(self, since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()
        for label, url in self._pages:
            try:
                payload = self._load_payload(url)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("[{}] fetch failed for {}: {}", self.name, url, exc)
                continue
            for item in self._parse(payload, label=label, page_url=url):
                if item.id in seen:
                    continue
                seen.add(item.id)
                items.append(item)
        return [i for i in items if i.published_at >= since]

    def _load_payload(self, url: str) -> list[Any]:
        with httpx.Client(
            timeout=PAGE_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.5"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        match = _NUXT_RE.search(response.text)
        if match is None:
            raise ValueError("__NUXT_DATA__ not found")
        payload = json.loads(match.group(1))
        if not isinstance(payload, list):
            raise ValueError("unexpected __NUXT_DATA__ shape")
        return payload

    def _parse(self, payload: list[Any], *, label: str, page_url: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        for node in payload:
            if not isinstance(node, dict):
                continue
            entry = {_deref_key(payload, key): value for key, value in node.items()}
            if not entry.keys() >= _NEWS_KEYS:
                continue

            title = _text(payload, entry.get("ueberschrift"))
            published = _date(payload, entry.get("datum"))
            if not title or published is None:
                continue

            kurztext = _rich_text(payload, entry.get("kurztext"))
            snippet = f"ILB-Förderung {label}"
            if kurztext:
                snippet = f"{snippet} | {kurztext}"

            items.append(
                NewsItem(
                    # Die Meldungen haben keine eigene Route — Identität ist
                    # (Übersichtsseite + Überschrift + Datum).
                    id=stable_id(f"{page_url}|{title}|{published.date().isoformat()}"),
                    source=self.name,
                    title=title,
                    url=page_url,
                    published_at=published,
                    snippet=snippet,
                )
            )
        return items


# ---------------------------------------------------------------------------
# Nuxt-Payload-Helfer
#
# Nuxt 3 liefert einen flachen Array aus: jeder Wert innerhalb eines Objekts
# oder einer Liste ist ein *Index* in denselben Array, keine Inline-Daten.
# Auch die Objekt-Schlüssel sind so kodiert.
# ---------------------------------------------------------------------------


def _deref(payload: list[Any], ref: Any) -> Any:
    """Einen Payload-Index auflösen; Nicht-Indizes unverändert zurückgeben."""
    if isinstance(ref, int) and not isinstance(ref, bool) and 0 <= ref < len(payload):
        return payload[ref]
    return ref


def _deref_key(payload: list[Any], key: Any) -> Any:
    return _deref(payload, int(key)) if isinstance(key, str) and key.isdigit() else key


def _text(payload: list[Any], ref: Any) -> str:
    value = _deref(payload, ref)
    return value.strip() if isinstance(value, str) else ""


def _date(payload: list[Any], ref: Any) -> datetime | None:
    """`["Date", "2026-08-12T09:00:00.000Z"]` — beide Teile sind Referenzen."""
    value = _deref(payload, ref)
    if not isinstance(value, list):
        return None
    for part in value:
        raw = _deref(payload, part)
        if isinstance(raw, str) and raw[:4].isdigit() and "-" in raw:
            return parse_datetime(raw)
    return None


def _rich_text(payload: list[Any], ref: Any, depth: int = 0) -> str:
    """Klartext aus dem verschachtelten Rich-Text-Baum der Meldung."""
    if depth > _MAX_DEPTH:
        return ""
    value = _deref(payload, ref)
    if isinstance(value, str):
        return value.strip()
    parts: list[str] = []
    if isinstance(value, list):
        for child in value:
            parts.append(_rich_text(payload, child, depth + 1))
    elif isinstance(value, dict):
        entry = {_deref_key(payload, key): item for key, item in value.items()}
        # Nur Textknoten beitragen; `data` trägt Formatierungs-Metadaten.
        if _text(payload, entry.get("type")) == "text":
            parts.append(_text(payload, entry.get("content")))
        elif "content" in entry:
            parts.append(_rich_text(payload, entry["content"], depth + 1))
    return " ".join(part for part in parts if part).strip()
