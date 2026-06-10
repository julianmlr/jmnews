"""Telegram chat bot — two-way conversation with tool-use.

Runs in a worker thread alongside the cron daemon. Long-polls Telegram
for new messages, accepts only the configured chat_id, and feeds the
conversation through Claude with three tools:

- `search_items`: full-text-ish DB search across all collected items
- `get_briefing`: fetch a stored briefing's markdown by ISO date
- `list_sources`: enumerate registered source names

Each chat is single-threaded (one in-flight request per chat_id) to
keep token costs and DB contention predictable. History rolls at the
configured limit (default 20 messages each direction = 40 in DB).

Slash commands:
  /reset    — clear the chat history for this chat
  /briefing — fetch today's briefing markdown

Everything else is passed verbatim to Claude with the profile + most
recent briefing pre-loaded as system context.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger
from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from jmnews.config import Settings
from jmnews.storage import Storage

CHAT_SYSTEM = """Du bist JMs persönlicher News-Assistent im Telegram-Chat.

Du sprichst JM direkt an (Du-Form, präzise, knapp). Antworten in Markdown,
maximal ~500 Wörter pro Antwort wenn nicht explizit länger gewünscht.

# Kontext
- Du kennst JMs Profil (siehe System-Block oben).
- Du hast Zugriff auf die jmnews-Datenbank (alle gesammelten Items der
  letzten 30 Tage) über das Tool `search_items`.
- Du kannst die zuletzt versendeten Briefings über `get_briefing` abrufen.
- Du kannst die aktiven Quellen-Liste über `list_sources` abrufen.

# Werkzeug-Nutzung
- Nutze `search_items` wenn JM nach einem konkreten Item / Thema fragt
  ("Was war das mit Lenitas?", "Zeig mir alle Vergabe-Items aus Brandenburg")
- Nutze `get_briefing` wenn er das Briefing eines bestimmten Tages will
  ("zeig mir das gestrige Briefing nochmal")
- Antworte NIE auf Basis spekulativer Annahmen — wenn du kein Item findest,
  sag das ehrlich.

# Antwort-Stil
- Direkt, knapp, ohne Floskeln ("Klar, gerne, hier ist...")
- Bei Listen: max 5 Items, weiter mit "(mehr im Briefing)" wenn nötig
- URLs immer als Markdown-Link [Quelle](url) wenn vorhanden
- Bei Fragen ohne klaren News-Bezug (z.B. "Wie spät ist es in Lugano?")
  antworte trotzdem hilfsbereit, aber kurz — keine künstliche
  Beschäftigungstherapie."""


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "search_items",
            "description": (
                "Search the jmnews items table (max 30 days back). All filters "
                "optional; combine to narrow. Returns up to `limit` items, "
                "each with title, source, category, score, published_at, url, "
                "snippet, reasoning."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Substring to match in title or snippet.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source name, e.g. 'insolvenz', 'baulinks'.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["action", "relevant", "context", "ignore"],
                    },
                    "since_days": {
                        "type": "integer",
                        "default": 30,
                        "description": "Lookback window in days (1-30).",
                    },
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "name": "get_briefing",
            "description": (
                "Return the markdown of the briefing for the given ISO date "
                "(YYYY-MM-DD). If omitted, returns the most recent briefing."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "briefing_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD; omit for latest.",
                    },
                },
            },
        },
        {
            "name": "list_sources",
            "description": "List all registered source names.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


def _run_tool(name: str, args: dict[str, Any], storage: Storage) -> str:
    if name == "search_items":
        items = storage.search_items(
            query=args.get("query"),
            source=args.get("source"),
            category=args.get("category"),
            since_days=int(args.get("since_days", 30)),
            limit=int(args.get("limit", 10)),
        )
        return json.dumps(
            [
                {
                    "id": it.id,
                    "title": it.title,
                    "source": it.source,
                    "category": it.category,
                    "score": it.score,
                    "published_at": it.published_at.isoformat() if it.published_at else None,
                    "url": it.url,
                    "snippet": (it.snippet or "")[:300],
                    "reasoning": (it.reasoning or "")[:200],
                }
                for it in items
            ],
            ensure_ascii=False,
        )
    if name == "get_briefing":
        briefing_date = args.get("briefing_date")
        if briefing_date:
            br = storage.get_briefing(briefing_date)
        else:
            # Walk back up to 14 days for the latest available briefing.
            br = None
            today = date.today()
            for delta in range(0, 14):
                d = (today - timedelta(days=delta)).isoformat()
                br = storage.get_briefing(d)
                if br:
                    break
        if not br:
            return json.dumps({"error": "no briefing found"})
        return json.dumps(
            {"id": br.id, "generated_at": br.generated_at.isoformat(), "markdown": br.markdown},
            ensure_ascii=False,
        )
    if name == "list_sources":
        from jmnews.sources import enabled_sources

        return json.dumps([s.name for s in enabled_sources()])
    return json.dumps({"error": f"unknown tool {name}"})


class ChatBot:
    """Conversational layer atop the briefing pipeline."""

    def __init__(self, settings: Settings, storage: Storage) -> None:
        self._settings = settings
        self._storage = storage
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._profile_text = Path(settings.profile_path).read_text(encoding="utf-8")
        self._allowed_chat_id: int | None = (
            int(settings.telegram_chat_id) if settings.telegram_chat_id else None
        )
        # Per-chat lock prevents overlapping LLM calls for the same chat.
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, chat_id: int) -> asyncio.Lock:
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    def _allowed(self, chat_id: int) -> bool:
        return self._allowed_chat_id is not None and chat_id == self._allowed_chat_id

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.message is None or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        if not self._allowed(chat_id):
            logger.warning("chat: rejecting unauthorized chat_id={}", chat_id)
            return
        text = (update.message.text or "").strip()
        if not text:
            return
        async with self._lock(chat_id):
            try:
                reply = await asyncio.to_thread(self._answer, chat_id, text)
            except Exception as exc:  # noqa: BLE001
                logger.exception("chat: answer failed: {}", exc)
                reply = f"⚠️ Internal error: {exc}"
            # Send as plain text — Telegram MARKDOWN_V1 chokes on any
            # unescaped `_`, `*`, `[`, `]`, MARKDOWN_V2 chokes on more.
            # Sonnet's Markdown looks acceptable rendered as plain text
            # (bullets and ** survive; links degrade to "text (url)").
            await update.message.reply_text(reply[:4000])

    async def handle_reset(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.message is None or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        if not self._allowed(chat_id):
            return
        n = self._storage.clear_chat(chat_id)
        await update.message.reply_text(f"🧹 Chat-Verlauf gelöscht ({n} Nachrichten).")

    async def handle_briefing(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.message is None or update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        if not self._allowed(chat_id):
            return
        today = date.today()
        br = None
        for delta in range(0, 14):
            d = (today - timedelta(days=delta)).isoformat()
            br = self._storage.get_briefing(d)
            if br:
                break
        if not br:
            await update.message.reply_text("Kein Briefing der letzten 14 Tage in der DB.")
            return
        await update.message.reply_text(br.markdown[:4000])

    def _answer(self, chat_id: int, user_text: str) -> str:
        """Sync Claude call (called via asyncio.to_thread).

        Loads rolling history, runs up to 5 tool-use rounds, persists the
        user message and final assistant reply.
        """
        history = self._storage.recent_chat(chat_id, limit=self._settings.chat_history_limit)
        self._storage.append_chat(chat_id, "user", user_text)

        messages: list[dict[str, Any]] = []
        for role, content in history:
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})

        for _ in range(5):
            response = self._client.messages.create(
                model=self._settings.chat_model,
                max_tokens=self._settings.chat_max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": self._profile_text,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": CHAT_SYSTEM},
                ],
                tools=_tool_definitions(),
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                text = _extract_text(response)
                self._storage.append_chat(chat_id, "assistant", text)
                return text

            # Capture the assistant turn (text + tool_use blocks) for the next iteration.
            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    result = _run_tool(block.name, dict(block.input), self._storage)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        text = "⚠️ Tool-Loop überschritten (5 Runden). Bitte umformulieren."
        self._storage.append_chat(chat_id, "assistant", text)
        return text


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip() or "(leere Antwort)"


def run_in_thread(settings: Settings, storage: Storage) -> threading.Thread:
    """Start the Telegram polling loop in a daemon thread.

    Returns the thread immediately; caller need not join it. The thread
    sets up its own asyncio event loop so it coexists peacefully with the
    APScheduler BlockingScheduler in the main thread.
    """
    if not settings.chat_enabled:
        logger.info("chat: disabled via JMNEWS_CHAT_ENABLED=0")
        return threading.Thread(target=lambda: None)
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("chat: TELEGRAM_BOT_TOKEN/CHAT_ID missing — chat disabled")
        return threading.Thread(target=lambda: None)

    bot = ChatBot(settings, storage)

    def _runner() -> None:
        asyncio.set_event_loop(asyncio.new_event_loop())
        app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )
        app.add_handler(CommandHandler("reset", bot.handle_reset))
        app.add_handler(CommandHandler("briefing", bot.handle_briefing))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
        logger.info("chat: Telegram polling started")
        try:
            app.run_polling(stop_signals=None, close_loop=False)
        except (TelegramError, RuntimeError) as exc:
            logger.error("chat: polling crashed: {}", exc)

    th = threading.Thread(target=_runner, name="jmnews-chat", daemon=True)
    th.start()
    return th


# Re-export for tests / external use
__all__ = ["ChatBot", "run_in_thread"]


# Bot is referenced as a docstring-only entity for mypy strict mode
_ = Bot  # noqa: B018
