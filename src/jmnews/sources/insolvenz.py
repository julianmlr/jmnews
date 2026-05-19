"""Bundesweites Insolvenzportal — early M&A signal for Kita / Jugendhilfe Träger.

`neu.insolvenzbekanntmachungen.de` is the official portal of all German
Insolvenzgerichte. We POST four wildcard searches per run (`*Kita*`,
`*Kinder*`, `*Jugend*`, `*Erzieh*`) covering the last 30 days, merge the
result tables, and apply a conservative client-side filter to drop false
positives (Familiennamen wie "Kindermann", Möbel/Spielzeug/Zahnpflege etc.).

Insolvency proceedings against social-sector Träger are an early signal:
SBW/Sophien Hof can approach the Insolvenzverwalter for asset-deal
takeover of the einrichtungs operations.

The portal is a JSF (Jakarta Faces / Mojarra) app:
- Form POST requires the ViewState hidden field from the prior GET
- jsessionid is in the form action URL (and in cookies)
- Wildcard column "*" is mode value `0`; "*Term*" matches as substring
- Result rows live in `table.ergebnis` with stable `tbl_ergebnis:N:otx_*` ids

We deliberately do not fetch the full Bekanntmachungstext (it's loaded
via mojarra.ab AJAX): the row metadata (Aktenzeichen, Gericht, Schuldner-
Bezeichnung, Sitz, Registereintrag) is enough for JM's daily triage.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import HTTP_TIMEOUT, USER_AGENT, Source, parse_datetime

BASE = "https://neu.insolvenzbekanntmachungen.de"
SEARCH_URL = f"{BASE}/ap/suche.jsf"

WILDCARDS = ("*Kita*", "*Kinder*", "*Jugend*", "*Erzieh*", "*Familien*", "*Sophien*")
LOOKBACK_DAYS = 30

# Schuldnername muss mindestens eines dieser Tokens enthalten, damit das
# Item überhaupt durchgereicht wird. Die JSF-Suche matcht stumpf auf
# Substring — "Kindermöbel", "Batkitar" (Familienname) etc. landen sonst
# als false positives im Briefing.
_RELEVANT_TOKENS = re.compile(
    r"\b("
    r"kita|kindertag|kindertages|kindergarten|krippe|hort|"
    r"kinderhaus|kinderheim|kinderhilfe|kinderbetreuung|"
    r"jugendhilfe|jugendamt|jugendhaus|jugendwerk|jugendzentrum|jugendwohn|"
    r"jugendclub|jugendtreff|jugendsozial|jugendförder|"
    r"erziehungshilfe|erziehungsstelle|erziehung\s|pädagog|"
    r"wohngruppe|familienzentrum|familienhilfe|familienpflege|familienservice|"
    r"familienberatung|tagesstätte|tagespflege|"
    r"sozialpädagog|integrationshilfe|heimerziehung|"
    r"sophien|sophiechen"
    r")\b",
    re.IGNORECASE,
)

# Negativliste — Branchen, die zufällig Stichworte enthalten aber für
# Träger-Übernahmen irrelevant sind.
_EXCLUDE_TOKENS = re.compile(
    r"\b("
    r"möbel|spielzeug|verlag|buchhandel|fahrschule|"
    r"zahnpflege|zahnarzt|zahnmedizin|"
    r"kleidung|mode|kosmetik|fußball|sportverein|"
    r"getränk|nahrungsmittel|gastronomie|restaurant|imbiss"
    r")\b",
    re.IGNORECASE,
)


class Insolvenz(Source):
    """Polls the federal insolvency portal for Kita/Jugendhilfe Träger."""

    name = "insolvenz"

    def fetch(self, since: datetime) -> list[NewsItem]:
        until = datetime.now(tz=since.tzinfo).date()
        since_date = max(
            since.date(),
            until - timedelta(days=LOOKBACK_DAYS),
        )
        items_by_id: dict[str, NewsItem] = {}
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "de,en;q=0.5",
            },
        ) as client:
            for term in WILDCARDS:
                try:
                    rows = self._search(client, term, since_date, until)
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "[{}] search for {!r} failed: {}", self.name, term, exc
                    )
                    continue
                for row in rows:
                    item = self._row_to_item(row)
                    if item is None:
                        continue
                    if item.published_at.date() < since_date:
                        continue
                    items_by_id.setdefault(item.id, item)
        return list(items_by_id.values())

    def _search(
        self,
        client: httpx.Client,
        firma: str,
        since_date: Any,
        until: Any,
    ) -> list[dict[str, str]]:
        """Submit one wildcard query and return list of result rows."""
        r = client.get(SEARCH_URL)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        forms = soup.find_all("form")
        if len(forms) < 3:
            raise ValueError("Search form not present")
        form = forms[2]
        action = form.get("action") or "/ap/suche.jsf"
        vs_input = soup.find("input", {"name": "jakarta.faces.ViewState"})
        if vs_input is None or not vs_input.get("value"):
            raise ValueError("ViewState missing")

        payload = {
            "frm_suche": "frm_suche",
            "frm_suche:lsom_bundesland:lsom": "",
            "frm_suche:lsom_gericht:lsom": "",
            "frm_suche:ldi_datumVon:datumHtml5": since_date.strftime("%Y-%m-%d"),
            "frm_suche:ldi_datumBis:datumHtml5": until.strftime("%Y-%m-%d"),
            "frm_suche:lsom_wildcard:lsom": "0",  # 0 = "*"
            "frm_suche:litx_firmaNachName:text": firma,
            "frm_suche:litx_vorname:text": "",
            "frm_suche:litx_sitzWohnsitz:text": "",
            "frm_suche:iaz_aktenzeichen:sbc_ohneAbteilung": "",
            "frm_suche:iaz_aktenzeichen:itx_abteilung": "",
            "frm_suche:iaz_aktenzeichen:som_registerzeichen": "",
            "frm_suche:iaz_aktenzeichen:itx_lfdNr": "",
            "frm_suche:iaz_aktenzeichen:itx_jahr": "",
            "frm_suche:lsom_gegenstand:lsom": "",
            "frm_suche:ireg_registereintrag:som_registergericht": "",
            "frm_suche:ireg_registereintrag:som_registerart": "",
            "frm_suche:ireg_registereintrag:itx_registernummer": "",
            "frm_suche:cbt_suchen": "Suchen",
            "jakarta.faces.ViewState": vs_input["value"],
        }
        post_url = action if action.startswith("http") else f"{BASE}{action}"
        r2 = client.post(post_url, data=payload)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "html.parser")
        table = soup2.find("table", id="tbl_ergebnis")
        if table is None:
            return []
        rows: list[dict[str, str]] = []
        for tr in table.select("tbody > tr"):
            row = {}
            for span in tr.find_all("span", id=True):
                key = span["id"].rsplit(":", 1)[-1]  # otx_datum, otx_azAkt, ...
                row[key] = span.get_text(" ", strip=True)
            if row:
                rows.append(row)
        return rows

    def _row_to_item(self, row: dict[str, str]) -> NewsItem | None:
        schuldner = row.get("otx_schuldner", "").strip()
        if not schuldner:
            return None
        # Drop natural persons (Schuldnerbezeichnung = "Nachname, Vorname")
        # The portal records natural persons with a leading comma-separated
        # surname; legal entities ("Müller GmbH", "Sophien e.V.") do not.
        if "," in schuldner:
            head = schuldner.split(",", 1)[0]
            if " " not in head and not any(
                w in schuldner.lower()
                for w in ("gmbh", "e.v.", "gemeinnützig", "stiftung", "ug ", "ag")
            ):
                return None
        if not _RELEVANT_TOKENS.search(schuldner):
            return None
        if _EXCLUDE_TOKENS.search(schuldner):
            return None

        aktenzeichen = row.get("otx_azAkt", "").strip()
        gericht = row.get("otx_Gericht", "").strip()
        sitz = row.get("otx_Sitz", "").strip()
        register = row.get("otx_register", "").strip()
        datum = row.get("otx_datum", "").strip()
        if not (aktenzeichen and gericht and datum):
            return None

        try:
            published = parse_datetime(datum)
        except Exception:  # noqa: BLE001
            return None

        snippet_parts = [
            f"Insolvenz {gericht}",
            f"Az. {aktenzeichen}",
            f"Sitz: {sitz}" if sitz else "",
            register,
        ]
        snippet = " | ".join(p for p in snippet_parts if p)

        return NewsItem(
            id=stable_id(f"insolv:{gericht}:{aktenzeichen}"),
            source=self.name,
            title=schuldner,
            url=SEARCH_URL,  # portal has no stable per-item URL (JSF AJAX detail)
            published_at=published,
            snippet=snippet,
        )
