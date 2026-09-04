"""TED (EU) — German public software/IT tenders, low-reference-hurdle first.

Every German award above the EU thresholds must be published on TED, whichever
state platform it originates from, so one API query covers all 16 Länder. The
API is free and needs no key.

Two filters carry the intent:

- ``notice-type = cn-standard`` keeps actual open opportunities and drops
  award notices (``can-*``), which are no longer biddable.
- ``procedure-type = open`` keeps the single-stage Offenes Verfahren, where
  anyone may submit an offer directly, and drops ``neg-w-call`` /
  ``restricted`` — the two-stage procedures that gate you behind a
  Teilnahmewettbewerb with reference requirements. Measured over 30 days:
  439 open vs. 127 reference-gated, so this is the bulk of the market, not a
  fringe.

Caveat worth keeping in mind when reading the results: ``open`` means no
*pre-qualification round*. An Offenes Verfahren can still demand references in
its Eignungskriterien, and those live in the Vergabeunterlagen, not in the
notice — so this narrows the field, it does not prove "no references".

TED only covers *above* the EU thresholds. The smaller, typically less
reference-heavy contracts are below them and never appear here; those come
from the state portals (see vergabe_software_laender).
"""

from __future__ import annotations

import contextlib
from datetime import datetime

import httpx
from loguru import logger

from jmnews.models import NewsItem, stable_id
from jmnews.sources.base import HTTP_TIMEOUT, USER_AGENT, Source, parse_datetime

SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

# 72* = IT services (development, consulting), 48* = software packages.
CPV_CODES: tuple[str, ...] = (
    "72000000",
    "72200000",
    "72212000",
    "72230000",
    "72260000",
    "48000000",
    "48900000",
)
# Single-stage procedures only — see module docstring.
PROCEDURE_TYPES: tuple[str, ...] = ("open",)
LOOKBACK_DAYS = 14
PAGE_LIMIT = 100

_FIELDS = [
    "publication-number",
    "title-proc",
    "buyer-name",
    "publication-date",
    "deadline-date-lot",
    "estimated-value-lot",
    "procedure-type",
]


def build_query(
    *,
    cpv_codes: tuple[str, ...] = CPV_CODES,
    procedure_types: tuple[str, ...] = PROCEDURE_TYPES,
    lookback_days: int = LOOKBACK_DAYS,
) -> str:
    return (
        f"classification-cpv IN ({' '.join(cpv_codes)}) "
        "AND buyer-country IN (DEU) "
        f"AND publication-date >= today(-{lookback_days}) "
        "AND notice-type IN (cn-standard) "
        f"AND procedure-type IN ({' '.join(procedure_types)})"
    )


def _first(value: object, lang: str = "deu") -> str:
    """TED returns multilingual dicts and single-element lists — unwrap both."""
    if isinstance(value, dict):
        picked = value.get(lang) or next(iter(value.values()), None)
        value = picked
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value is not None else ""


class VergabeSoftwareTED(Source):
    name = "vergabe_software_ted"

    def fetch(self, since: datetime) -> list[NewsItem]:
        try:
            notices = self._search()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] TED search failed: {}", self.name, exc)
            return []
        items = [i for i in (self._to_item(n) for n in notices) if i is not None]
        return [i for i in items if i.published_at >= since]

    def _search(self) -> list[dict]:
        payload = {"query": build_query(), "fields": _FIELDS, "limit": PAGE_LIMIT}
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.post(
                SEARCH_URL,
                json=payload,
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json().get("notices", []) or []

    def _to_item(self, notice: dict) -> NewsItem | None:
        number = _first(notice.get("publication-number"))
        title = _first(notice.get("title-proc"))
        if not number or not title:
            return None

        url = f"https://ted.europa.eu/de/notice/{number}"
        buyer = _first(notice.get("buyer-name"))
        deadline = _first(notice.get("deadline-date-lot"))[:10]
        value = _first(notice.get("estimated-value-lot"))

        parts = ["Offenes Verfahren (keine Referenz-Vorrunde)"]
        if buyer:
            parts.append(buyer)
        if deadline:
            parts.append(f"Frist: {deadline}")
        if value:
            with contextlib.suppress(ValueError):
                parts.append(f"Wert: {int(float(value)):,} EUR".replace(",", "."))

        return NewsItem(
            id=stable_id(url),
            source=self.name,
            title=title,
            url=url,
            published_at=parse_datetime(_first(notice.get("publication-date"))[:10]),
            snippet=" | ".join(parts),
        )
