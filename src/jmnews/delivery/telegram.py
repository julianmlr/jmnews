"""Telegram delivery: sends the briefing in one message per section.

We render Telegram HTML (not MarkdownV2) because HTML escaping is trivial and
unambiguous: only `&`, `<`, `>` need escaping, the rest of the text is safe.
This matches the anti-haenger spec rule: don't fight Markdown escaping.

Order of preference per section:
1. HTML formatted (bold/italic/links)
2. Plain text (no parse mode)
3. If all sections fail, write to data/briefings/<date>.md
"""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from loguru import logger
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from jmnews.config import Settings
from jmnews.models import Briefing

DeliveryStatus = Literal["telegram", "file", "failed"]

TG_MESSAGE_LIMIT = 4000  # leave headroom under 4096 hard limit

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_ITALIC_UNDERSCORE_RE = re.compile(r"(?<![A-Za-z0-9_])_([^_\n]+)_(?![A-Za-z0-9_])")


class TelegramDelivery:
    """Sends a Briefing to Telegram, with file fallback."""

    def __init__(self, settings: Settings) -> None:
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id
        self._briefings_dir = Path(settings.briefings_dir)

    def deliver(self, briefing: Briefing) -> DeliveryStatus:
        sections = _split_into_sections(briefing.markdown)
        if not self._token or not self._chat_id:
            logger.warning("Telegram not configured; writing briefing to file")
            return self._write_file(briefing)

        try:
            asyncio.run(self._send_all(sections))
        except Exception as exc:  # noqa: BLE001
            logger.error("All Telegram delivery attempts failed: {}", exc)
            return self._write_file(briefing)
        return "telegram"

    async def _send_all(self, sections: list[str]) -> None:
        bot = Bot(token=self._token)
        async with bot:
            for section in sections:
                await self._send_one(bot, section)

    async def _send_one(self, bot: Bot, section: str) -> None:
        html_text = _markdown_to_html(section)
        for chunk in _chunk_text(html_text, TG_MESSAGE_LIMIT):
            try:
                await bot.send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except TelegramError as exc:
                logger.warning(
                    "Telegram HTML send failed ({}); retrying as plain text",
                    exc,
                )
                plain = _strip_markdown(section)
                for plain_chunk in _chunk_text(plain, TG_MESSAGE_LIMIT):
                    await bot.send_message(
                        chat_id=self._chat_id,
                        text=plain_chunk,
                        disable_web_page_preview=True,
                    )
                # one plain fallback per section is enough; stop chunk loop
                return

    def _write_file(self, briefing: Briefing) -> DeliveryStatus:
        try:
            self._briefings_dir.mkdir(parents=True, exist_ok=True)
            path = self._briefings_dir / f"{briefing.id}.md"
            path.write_text(briefing.markdown, encoding="utf-8")
            logger.info("Briefing written to {}", path)
            return "file"
        except OSError as exc:
            logger.error("Failed writing briefing file: {}", exc)
            return "failed"


def _split_into_sections(markdown: str) -> list[str]:
    """Split markdown so each H2 section is one message; preamble + H1 go first."""
    lines = markdown.splitlines()
    sections: list[list[str]] = [[]]
    for line in lines:
        if line.startswith("## "):
            sections.append([line])
        else:
            sections[-1].append(line)
    return ["\n".join(s).strip() for s in sections if any(line.strip() for line in s)]


def _markdown_to_html(text: str) -> str:
    """Convert our briefing markdown subset to Telegram HTML.

    Supported: `# H1`, `## H2` → bold; `**bold**` → <b>; `*italic*` /
    `_italic_` → <i>; `[text](url)` → <a>; bullet lists rendered as `- `.
    Everything else is HTML-escaped.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("### "):
            out_lines.append(f"<b>{html.escape(line[4:].strip())}</b>")
        elif line.startswith("## "):
            out_lines.append(f"<b>{html.escape(line[3:].strip())}</b>")
        elif line.startswith("# "):
            out_lines.append(f"<b>{html.escape(line[2:].strip())}</b>")
        else:
            out_lines.append(_render_inline(line))
    return "\n".join(out_lines)


def _render_inline(line: str) -> str:
    """Render inline markdown to HTML using placeholder-substitution to keep
    escapes from clobbering tags.
    """
    placeholders: list[str] = []

    def _store(tag: str) -> str:
        placeholders.append(tag)
        return f"\x00{len(placeholders) - 1}\x00"

    def _link(m: re.Match[str]) -> str:
        text = html.escape(m.group(1))
        url = html.escape(m.group(2), quote=True)
        return _store(f'<a href="{url}">{text}</a>')

    def _bold(m: re.Match[str]) -> str:
        return _store(f"<b>{html.escape(m.group(1))}</b>")

    def _italic(m: re.Match[str]) -> str:
        return _store(f"<i>{html.escape(m.group(1))}</i>")

    line = _LINK_RE.sub(_link, line)
    line = _BOLD_RE.sub(_bold, line)
    line = _ITALIC_RE.sub(_italic, line)
    line = _ITALIC_UNDERSCORE_RE.sub(_italic, line)

    line = html.escape(line)

    def _restore(m: re.Match[str]) -> str:
        return placeholders[int(m.group(1))]

    return re.sub(r"\x00(\d+)\x00", _restore, line)


def _strip_markdown(text: str) -> str:
    """Best-effort plain-text rendering: keep titles + URLs visible."""
    text = _LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = _BOLD_RE.sub(lambda m: m.group(1), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text


def _chunk_text(text: str, limit: int) -> Iterable[str]:
    """Split text into chunks <= limit, breaking on newlines when possible."""
    if len(text) <= limit:
        yield text
        return
    buf: list[str] = []
    buf_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1  # include newline
        if buf and buf_len + line_len > limit:
            yield "\n".join(buf)
            buf, buf_len = [], 0
        if line_len > limit:
            # extremely long single line; hard-split
            for i in range(0, len(line), limit):
                yield line[i : i + limit]
        else:
            buf.append(line)
            buf_len += line_len
    if buf:
        yield "\n".join(buf)
