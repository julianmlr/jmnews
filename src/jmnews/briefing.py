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
Nutze die Items, die JMs Filter bereits als action / relevant / context klassifiziert hat.
Pro Item liest du zuerst die JM-Profil-Hinweise im System-Prompt nicht erneut vor,
sondern nutzt sie nur, um die JM-Implikation pro Action-Item knapp zu formulieren.

Halte dich strikt an dieses Template (Emojis exakt so uebernehmen):

# JM-Briefing {DATUM}

## 🔥 Aktion erforderlich
- **{Headline}**
  2-3 Saetze Kern.
  *JM-Implikation:* 1-2 Saetze.
  Quelle: [{source}]({url})

## 🎯 Wichtig zu lesen
- **{Headline}** - 1-2 Saetze. [{source}]({url})

## 📰 Kontext (Sammelmeldung)
- **{Stichwort}**: 1 Satz. [{source}]({url})

## ⏭️ Übersprungen heute
{N} Items als ignore klassifiziert.

Regeln:
- Wenn keine Action-Items: lass den ganzen "Aktion erforderlich"-Block weg.
- Wenn keine Relevant-Items: lass den Block weg. Analog fuer Kontext.
- Bei null Items insgesamt: schreibe "Keine relevanten Nachrichten heute." als Body.
- Keine Phantasie-Quellen, keine zusaetzlichen Sections."""


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

    parts = [
        f"Datum: {briefing_date.isoformat()}",
        f"Ignorierte Items heute: {ignored}",
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
    """Deterministic Markdown fallback when the LLM call fails."""
    out: list[str] = [
        f"# JM-Briefing {briefing_date.isoformat()}",
        "",
        "_LLM-Generierung fehlgeschlagen - Rohdaten:_",
        "",
    ]
    if groups["action"]:
        out.append("## 🔥 Aktion erforderlich")
        for it in groups["action"]:
            out.append(f"- **{it.title}** [{it.source}]({it.url})")
            if it.snippet:
                out.append(f"  {it.snippet}")
        out.append("")
    if groups["relevant"]:
        out.append("## 🎯 Wichtig zu lesen")
        for it in groups["relevant"]:
            out.append(f"- **{it.title}** [{it.source}]({it.url})")
        out.append("")
    if groups["context"]:
        out.append("## 📰 Kontext")
        for it in groups["context"]:
            out.append(f"- {it.title} [{it.source}]({it.url})")
        out.append("")
    out.append(f"## ⏭️ Übersprungen heute\n{ignored} Items als ignore klassifiziert.")
    return "\n".join(out).strip()
