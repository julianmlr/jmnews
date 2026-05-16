"""Generates the daily Markdown briefing from classified items via Claude Sonnet."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger

from jmnews.config import Settings
from jmnews.models import Briefing, Category, NewsItem

MAX_ACTION = 5
MAX_RELEVANT = 8
MAX_CONTEXT = 10
MAX_TOKENS = 4096
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 2.0

BRIEFING_SYSTEM = """Du bist JMs persoenlicher Redakteur fuer das taegliche Briefing.

Schreib praezise auf Deutsch, max. 1.500 Woerter, im Markdown-Format.
Nutze die Items, die JMs Filter bereits als action / relevant / context
klassifiziert hat. Pro Item nutzt du das JM-Profil im System-Prompt nur,
um die JM-Implikation pro Action-Item knapp zu formulieren - nicht um
Items neu zu bewerten.

# Standard-Template (Emojis exakt so uebernehmen):

# JM-Briefing {DATUM}

## 🚨 DRINGEND
- **{Headline}**
  2-3 Saetze Kern. Wenn eine Antragsfrist erwaehnt wird, nenne sie explizit
  ("Frist: TT.MM.JJJJ" oder "Bewerbung bis ...").
  *JM-Implikation:* 1-2 Saetze.
  Quelle: [{source}]({url})

## 🔥 HOCH
- **{Headline}** - 2-3 Saetze Kern. *JM-Implikation:* 1 Satz.
  Quelle: [{source}]({url})

## 🎯 MITTEL
- **{Headline}** - 1-2 Saetze. [{source}]({url})

## 📰 HINTERGRUND (Sammelmeldung)
- **{Stichwort}**: 1 Satz. [{source}]({url})

## ⏭️ Übersprungen heute
{N} Items als ignore klassifiziert.

# Mapping action/relevant/context -> Sections:
- DRINGEND: action-Items, bei denen aus Snippet/Titel eine Antragsfrist
  <14 Tage hervorgeht ODER eine akute Traegerausschreibung in
  Berlin/Brandenburg.
- HOCH: alle uebrigen action-Items + relevant-Items mit Score >= 7.
- MITTEL: relevant-Items mit Score 6.
- HINTERGRUND: context-Items (inkl. persoenliche Background-Themen wie
  Longevity, KI, Schweizer Wegzug - die gehoeren NICHT nach HOCH/MITTEL).

# Sonderformate (zusaetzlich am Ende, NACH "Uebersprungen heute"):

Wenn der User-Prompt enthaelt "Sonderformat aktiv: Mittwoch-Wochenrueckblick":
## 📅 Wochenrueckblick Traegeraufrufe
Alle heute zugefuehrten Items (egal welche Section), deren Titel oder
Snippet "Traegeraufruf", "Foerderaufruf", "Ausschreibung", "Bewerbung"
oder vergleichbares enthaelt - kompakt als Liste mit Frist sofern erkennbar.
Max 12 Items. Wenn keine passenden Items: Section komplett weglassen.

Wenn der User-Prompt enthaelt "Sonderformat aktiv: Monatsbilanz":
## 📊 Monats-Bilanz Foerderprogramme & Marktbeobachtung
Zwei Unterabschnitte aus den heute zugefuehrten Items:
- **Foerderprogramme**: alle Foerderprogramm-/Zuwendungs-Themen kompakt.
- **Markt- und Uebernahmebeobachtung**: Traegerwechsel, Insolvenzen,
  Schliessungen, Trägerausschreibungen.
Max je 8 Items pro Unterabschnitt. Leere Unterabschnitte weglassen.

# Regeln:
- Wenn eine Section leer ist, lass sie komplett weg (inkl. ##-Ueberschrift).
- Bei null Items insgesamt: schreibe nur "Keine relevanten Nachrichten heute."
- Keine Phantasie-Quellen, keine zusaetzlichen Sections.
- "Lieber knapp und hoch": im Zweifel ein Item in die hoehere Section
  schieben (HOCH statt MITTEL etc.) statt zu vielen MITTEL-Eintraegen.
- Persoenliche Background-Themen (Steuer, Wegzug Schweiz, Longevity, KI)
  gehoeren in HINTERGRUND - selbst wenn der Filter sie als "relevant" markiert.
"""


class BriefingGenerator:
    """Renders the daily briefing using Claude Sonnet, with a deterministic fallback."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if not settings.anthropic_api_key and client is None:
            raise RuntimeError("ANTHROPIC_API_KEY is required for BriefingGenerator")
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.briefing_model
        self._profile_text = Path(settings.profile_path).read_text(encoding="utf-8")

    def generate(
        self,
        items: list[NewsItem],
        briefing_date: date,
        *,
        ignored_count: int = 0,
    ) -> Briefing:
        groups = _group_items(items)
        # If caller didn't pass ignored_count, infer from items list as a fallback.
        if ignored_count == 0:
            ignored_count = sum(1 for i in items if i.category == "ignore")
        delivered_count = (
            len(groups["action"]) + len(groups["relevant"]) + len(groups["context"])
        )

        markdown = self._call_sonnet(groups, ignored_count, briefing_date)
        if markdown is None:
            logger.warning("Sonnet briefing failed; using deterministic fallback")
            markdown = _render_fallback(groups, ignored_count, briefing_date)

        return Briefing(
            id=briefing_date.isoformat(),
            generated_at=datetime.now(UTC),
            markdown=markdown,
            item_count=delivered_count,
        )

    def _call_sonnet(
        self,
        groups: dict[str, list[NewsItem]],
        ignored: int,
        briefing_date: date,
    ) -> str | None:
        user_prompt = _build_user_prompt(groups, ignored, briefing_date)
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=MAX_TOKENS,
                    system=[
                        {
                            "type": "text",
                            "text": self._profile_text,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": BRIEFING_SYSTEM},
                    ],
                    messages=[{"role": "user", "content": user_prompt}],
                )
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                wait = RETRY_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "Briefing API attempt {}/{} failed ({}); retrying in {}s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                continue

            text = _extract_text(response).strip()
            if text:
                return text
            logger.warning("Briefing response was empty (attempt {})", attempt + 1)
        return None


def _group_items(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
    def _key(i: NewsItem) -> int:
        return i.score if i.score is not None else 0

    by_cat: dict[Category, list[NewsItem]] = {
        "action": [],
        "relevant": [],
        "context": [],
        "ignore": [],
    }
    for item in items:
        if item.category in by_cat:
            by_cat[item.category].append(item)

    return {
        "action": sorted(by_cat["action"], key=_key, reverse=True)[:MAX_ACTION],
        "relevant": sorted(by_cat["relevant"], key=_key, reverse=True)[:MAX_RELEVANT],
        "context": sorted(by_cat["context"], key=_key, reverse=True)[:MAX_CONTEXT],
    }


_WEEKDAYS_DE = (
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
)


def _sonderformat_for(d: date) -> str:
    """Return the Sonderformat label active on this date, or empty string."""
    weekday = d.weekday()  # 0 = Monday
    if weekday == 2:
        return "Mittwoch-Wochenrueckblick"
    if weekday == 0 and d.day <= 7:
        return "Monatsbilanz"
    return ""


def _build_user_prompt(
    groups: dict[str, list[NewsItem]],
    ignored: int,
    briefing_date: date,
) -> str:
    def _block(label: str, items: list[NewsItem]) -> str:
        if not items:
            return f"{label}: keine\n"
        lines = [f"{label}:"]
        for it in items:
            lines.append(
                f"- id={it.id} score={it.score} source={it.source}\n"
                f"  title: {it.title}\n"
                f"  url: {it.url}\n"
                f"  snippet: {it.snippet}\n"
                f"  reasoning: {it.reasoning or ''}"
            )
        return "\n".join(lines) + "\n"

    weekday = _WEEKDAYS_DE[briefing_date.weekday()]
    sonderformat = _sonderformat_for(briefing_date)
    sonderformat_line = (
        f"Sonderformat aktiv: {sonderformat}"
        if sonderformat
        else "Sonderformat aktiv: keiner"
    )

    parts = [
        f"Datum: {briefing_date.isoformat()} ({weekday})",
        f"Ignorierte Items heute: {ignored}",
        sonderformat_line,
        "",
        _block("ACTION", groups["action"]),
        _block("RELEVANT", groups["relevant"]),
        _block("CONTEXT", groups["context"]),
        "Erzeuge jetzt das Briefing-Markdown nach dem Template.",
    ]
    return "\n".join(parts)


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def _render_fallback(
    groups: dict[str, list[NewsItem]],
    ignored: int,
    briefing_date: date,
) -> str:
    """Deterministic Markdown fallback when the LLM call fails.

    Uses a simplified mapping (all action -> DRINGEND, all relevant -> HOCH)
    since we can't apply the LLM's frist/score heuristic offline.
    """
    out: list[str] = [
        f"# JM-Briefing {briefing_date.isoformat()}",
        "",
        "_LLM-Generierung fehlgeschlagen - Rohdaten:_",
        "",
    ]
    if groups["action"]:
        out.append("## 🚨 DRINGEND")
        for it in groups["action"]:
            out.append(f"- **{it.title}** [{it.source}]({it.url})")
            if it.snippet:
                out.append(f"  {it.snippet}")
        out.append("")
    if groups["relevant"]:
        out.append("## 🔥 HOCH")
        for it in groups["relevant"]:
            out.append(f"- **{it.title}** [{it.source}]({it.url})")
        out.append("")
    if groups["context"]:
        out.append("## 📰 HINTERGRUND")
        for it in groups["context"]:
            out.append(f"- {it.title} [{it.source}]({it.url})")
        out.append("")
    out.append(f"## ⏭️ Übersprungen heute\n{ignored} Items als ignore klassifiziert.")
    return "\n".join(out).strip()
