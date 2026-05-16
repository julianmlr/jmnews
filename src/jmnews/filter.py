"""Claude-based pre-filter that classifies items against the JM profile."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger
from pydantic import ValidationError

from jmnews.config import Settings
from jmnews.models import FilterResult, NewsItem

USER_INSTRUCTION = """Klassifiziere die folgenden Nachrichten-Items gegen das JM-Profil im System.

Antworte AUSSCHLIESSLICH mit einem JSON-Array. Pro Item ein Objekt:
{
  "id": "uebernommen aus Input",
  "score": 0-10,
  "category": "ignore" | "context" | "relevant" | "action",
  "reasoning": "max. 1 Satz"
}

Reihenfolge im Output ist egal, aber jede Input-ID muss genau einmal vorkommen.

Items:
"""

MAX_TOKENS = 4096
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 2.0


class Filter:
    """Wraps an Anthropic client to batch-classify NewsItems."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: anthropic.Anthropic | None = None,
        profile_text: str | None = None,
    ) -> None:
        if not settings.anthropic_api_key and client is None:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Filter")
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.filter_model
        self._batch_size = max(1, settings.filter_batch_size)
        self._profile_text = profile_text or Path(settings.profile_path).read_text(
            encoding="utf-8"
        )

    def classify(self, items: Iterable[NewsItem]) -> list[FilterResult]:
        results: list[FilterResult] = []
        for batch in _chunked(list(items), self._batch_size):
            try:
                results.extend(self._classify_batch(batch))
            except Exception as exc:  # noqa: BLE001
                logger.error("Filter batch failed permanently: {}", exc)
        return results

    def _classify_batch(self, batch: list[NewsItem]) -> list[FilterResult]:
        prompt = USER_INSTRUCTION + json.dumps(
            [
                {
                    "id": item.id,
                    "source": item.source,
                    "title": item.title,
                    "snippet": item.snippet,
                }
                for item in batch
            ],
            ensure_ascii=False,
        )

        last_exc: Exception | None = None
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
                        }
                    ],
                    messages=[{"role": "user", "content": prompt}],
                )
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                last_exc = exc
                wait = RETRY_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "Filter API attempt {}/{} failed ({}); retrying in {}s",
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                continue

            text = _extract_text(response)
            parsed = _parse_response(text, batch)
            if parsed:
                return parsed
            logger.warning("Filter response unparsable; treating attempt as failure")
            last_exc = RuntimeError("unparsable filter response")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_SECONDS * (2**attempt))

        logger.error(
            "Filter batch of {} items failed after {} attempts: {}",
            len(batch),
            MAX_RETRIES,
            last_exc,
        )
        return []


def _chunked(seq: list[NewsItem], size: int) -> Iterator[list[NewsItem]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_response(text: str, batch: list[NewsItem]) -> list[FilterResult]:
    """Extract a JSON array of FilterResult objects from a model response."""
    candidate = text.strip()
    fence = _FENCE_RE.search(candidate)
    if fence:
        candidate = fence.group(1).strip()
    if not candidate.startswith("["):
        start = candidate.find("[")
        end = candidate.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        candidate = candidate[start : end + 1]

    try:
        raw = json.loads(candidate)
    except json.JSONDecodeError as exc:
        logger.warning("Filter JSON parse failed: {}", exc)
        return []

    if not isinstance(raw, list):
        return []

    known_ids = {item.id for item in batch}
    results: list[FilterResult] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") not in known_ids:
            continue
        try:
            results.append(FilterResult(**entry))
        except ValidationError as exc:
            logger.warning("Skipping invalid filter result {}: {}", entry, exc)
    return results
