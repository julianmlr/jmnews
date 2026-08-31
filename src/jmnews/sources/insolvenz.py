"""Bundesweites Insolvenzportal — early M&A signal for Kita / Jugendhilfe Träger.

`neu.insolvenzbekanntmachungen.de` is the official portal of all German
Insolvenzgerichte. We POST one wildcard search per WILDCARDS entry per run
(`*Kita*`, `*Kinder*`, `*Wohngrupp*`, `*Pädagog*` …) covering the last 30
days, merge the result tables, and apply a conservative client-side stem
filter to drop false positives (Familiennamen wie "Kindermann",
Möbel/Spielzeug/Zahnpflege etc.).

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

# Name-based portal search. `*Erzieh*` already catches "Heimerziehung",
# `*Kinder*` catches "Kinderdorf/-haus/-heim". `*Wohngrupp*` and `*Pädagog*`
# add the neutrally-named stationäre-Jugendhilfe operators ("Wohngruppen …
# gGmbH", "Sozialpädagogisches Zentrum …") that carry none of the other stems.
WILDCARDS = (
    "*Kita*", "*Kinder*", "*Jugend*", "*Erzieh*", "*Familien*",
    "*Wohngrupp*", "*Pädagog*", "*Sophien*",
)
LOOKBACK_DAYS = 30

# Schuldnername muss mindestens eines dieser Stems enthalten, damit das Item
# durchgereicht wird — die JSF-Suche matcht stumpf auf Substring, "Kindermöbel"
# / "Batkitar" (Familienname) landen sonst als false positives im Briefing.
#
# PREFIX-Match (nur führendes \b, KEIN abschließendes): deutsche Komposita wie
# "Kindertagesstätte", "Wohngruppen" (Plural), "Sozialpädagogisches" fielen mit
# abschließender Wortgrenze sonst durch (der Stem endet mitten im Wort).
_RELEVANT_STEMS = (
    "kita", "kindertag", "kindergarten", "kinderkrippe",
    "kinderhaus", "kinderheim", "kinderhilfe", "kinderbetreuung", "kinderdorf",
    "jugendhilfe", "jugendamt", "jugendhaus", "jugendwerk", "jugendzentrum",
    "jugendwohn", "jugendclub", "jugendtreff", "jugendsozial", "jugendförder",
    "jugenddorf",
    "erziehungshilfe", "erziehungsstelle", "erziehungsbeistand", "heimerziehung",
    "wohngrupp", "familienzentrum", "familienhilfe", "familienpflege",
    "familienservice", "familienberatung", "tagesstätte", "tagespflege",
    "sozialpädagog", "heilpädagog", "pädagog", "integrationshilfe",
    "inobhutnahme", "sophien", "sophiechen",
)
_RELEVANT_TOKENS = re.compile(
    r"\b(?:" + "|".join(_RELEVANT_STEMS) + r")", re.IGNORECASE
)
# Kurze/mehrdeutige Tokens brauchen die abschließende Wortgrenze, sonst matchen
# sie Fremdwörter ("Hortensienweg", "Krippenstall").
_RELEVANT_SHORT = re.compile(r"\b(?:hort|krippe)\b", re.IGNORECASE)

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


def _form_defaults(form: Any) -> dict[str, str]:
    """Every named field of `form` with the value an untouched browser would send.

    Selects fall back to their first option (the portal's "no selection" entry,
    currently `NO_CODE`), unchecked boxes submit empty, everything else carries
    its rendered `value` — which is what supplies the JSF form marker and the
    `jakarta.faces.ViewState` token.
    """
    payload: dict[str, str] = {}
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "select":
            option = el.find("option")
            payload[name] = (option.get("value") or "") if option else ""
        elif el.get("type") in ("checkbox", "radio"):
            payload[name] = el.get("value", "") if el.has_attr("checked") else ""
        else:
            payload[name] = el.get("value") or ""
    return payload


def _field_name(payload: dict[str, str], suffix: str) -> str:
    """Resolve the full field name ending in `suffix`, else raise.

    Raising here is deliberate: `fetch` turns it into one warning naming the
    missing field, which is the signal that the portal renamed something —
    far easier to act on than the bare 500 a stale payload produces.
    """
    matches = [name for name in payload if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one field ending in {suffix!r}, got {matches}")
    return matches[0]


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
        form = soup.find("form", id="frm_suche")
        if form is None:
            raise ValueError("Search form frm_suche not present")

        # The portal renames its JSF field ids on redeploys (the naming-container
        # prefixes changed once already: `lsom_bundesland:lsom` became
        # `lsom_bundesland:codelist:scl_bundesland:mysom`). Posting a stale name
        # makes Mojarra answer 500 with no usable message, so we seed the payload
        # from the form that was actually served and only override the few fields
        # we care about, matched by their stable id suffix.
        payload = _form_defaults(form)
        for suffix, value in (
            ("ldi_datumVon:datumHtml5", since_date.strftime("%Y-%m-%d")),
            ("ldi_datumBis:datumHtml5", until.strftime("%Y-%m-%d")),
            ("lsom_wildcard:lsom", "0"),  # 0 = "*"
            ("litx_firmaNachName:text", firma),
        ):
            payload[_field_name(payload, suffix)] = value

        action = str(form.get("action") or "/ap/suche.jsf")
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
                key = str(span["id"]).rsplit(":", 1)[-1]  # otx_datum, otx_azAkt, ...
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
        if not (_RELEVANT_TOKENS.search(schuldner) or _RELEVANT_SHORT.search(schuldner)):
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
