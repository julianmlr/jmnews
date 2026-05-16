"""Tests for jmnews.delivery.telegram."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import BadRequest

from jmnews.config import Settings
from jmnews.delivery.telegram import (
    TelegramDelivery,
    _chunk_text,
    _markdown_to_html,
    _split_into_sections,
    _strip_markdown,
)
from jmnews.models import Briefing


def _settings(tmp_path: Path, *, configured: bool = True) -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN="123:ABC" if configured else "",
        TELEGRAM_CHAT_ID="42" if configured else "",
        JMNEWS_BRIEFINGS_DIR=tmp_path / "briefings",
        JMNEWS_PROFILE_PATH=tmp_path / "jm_profile.md",
    )


def _briefing(md: str = "# T\n\n## S1\nbody") -> Briefing:
    return Briefing(
        id="2026-05-16",
        generated_at=datetime.now(UTC),
        markdown=md,
        item_count=1,
    )


# ----- markdown→HTML conversion -----


def test_markdown_to_html_handles_headers() -> None:
    assert _markdown_to_html("# Title") == "<b>Title</b>"
    assert _markdown_to_html("## Section") == "<b>Section</b>"


def test_markdown_to_html_handles_bold_italic_links() -> None:
    out = _markdown_to_html("**bold** and *italic* with [link](https://e.com)")
    assert "<b>bold</b>" in out
    assert "<i>italic</i>" in out
    assert '<a href="https://e.com">link</a>' in out


def test_markdown_to_html_escapes_specials_in_text() -> None:
    out = _markdown_to_html("compare 1<2 & 3>2")
    assert "&lt;" in out
    assert "&gt;" in out
    assert "&amp;" in out


def test_markdown_to_html_escapes_inside_link_text() -> None:
    out = _markdown_to_html("[a<b](https://e.com?x=1&y=2)")
    assert '<a href="https://e.com?x=1&amp;y=2">a&lt;b</a>' in out


def test_markdown_to_html_does_not_double_escape_in_bold() -> None:
    out = _markdown_to_html("**A & B**")
    assert "<b>A &amp; B</b>" in out


# ----- section splitting -----


def test_split_into_sections_one_per_h2() -> None:
    md = "# Title\nIntro\n\n## A\nbody A\n\n## B\nbody B"
    sections = _split_into_sections(md)
    assert len(sections) == 3
    assert sections[0].startswith("# Title")
    assert sections[1].startswith("## A")
    assert sections[2].startswith("## B")


def test_split_skips_pure_whitespace_sections() -> None:
    md = "# Title\n\n## A\n\n"
    sections = _split_into_sections(md)
    # the trailing empty H2 still has the header, so it stays
    assert all(s.strip() for s in sections)


# ----- chunking -----


def test_chunk_text_breaks_on_newline() -> None:
    text = "a" * 30 + "\n" + "b" * 30 + "\n" + "c" * 30
    chunks = list(_chunk_text(text, limit=50))
    assert len(chunks) >= 2
    assert all(len(c) <= 50 for c in chunks)


def test_chunk_text_passes_short_text_through() -> None:
    assert list(_chunk_text("hello", limit=100)) == ["hello"]


# ----- plain-text fallback -----


def test_strip_markdown_keeps_url_and_text() -> None:
    out = _strip_markdown("**Bold** *it* [Title](https://e.com)")
    assert "Bold" in out
    assert "it" in out
    assert "Title" in out
    assert "https://e.com" in out
    assert "**" not in out
    assert "[" not in out


# ----- delivery integration -----


def test_deliver_writes_file_when_telegram_not_configured(tmp_path: Path) -> None:
    delivery = TelegramDelivery(_settings(tmp_path, configured=False))
    status = delivery.deliver(_briefing())
    assert status == "file"
    written = (tmp_path / "briefings" / "2026-05-16.md").read_text(encoding="utf-8")
    assert "## S1" in written


def test_deliver_sends_one_message_per_section(tmp_path: Path) -> None:
    md = "# Title\nIntro\n\n## A\nbody A\n\n## B\nbody B"
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.__aenter__ = AsyncMock(return_value=bot)
    bot.__aexit__ = AsyncMock(return_value=None)

    with patch("jmnews.delivery.telegram.Bot", return_value=bot):
        delivery = TelegramDelivery(_settings(tmp_path))
        status = delivery.deliver(_briefing(md))

    assert status == "telegram"
    assert bot.send_message.call_count == 3
    # First call carries the title
    first = bot.send_message.call_args_list[0].kwargs
    assert "<b>Title</b>" in first["text"]
    assert first["parse_mode"] == "HTML"


def test_deliver_falls_back_to_plain_text_on_html_badrequest(tmp_path: Path) -> None:
    md = "# T\n\n## S\nbody"
    bot = MagicMock()

    sent: list[dict] = []

    async def send(**kwargs):  # noqa: ANN003
        sent.append(kwargs)
        if kwargs.get("parse_mode") == "HTML":
            raise BadRequest("can't parse entities")
        return None

    bot.send_message = AsyncMock(side_effect=send)
    bot.__aenter__ = AsyncMock(return_value=bot)
    bot.__aexit__ = AsyncMock(return_value=None)

    with patch("jmnews.delivery.telegram.Bot", return_value=bot):
        delivery = TelegramDelivery(_settings(tmp_path))
        status = delivery.deliver(_briefing(md))

    assert status == "telegram"
    # at least one HTML attempt and one plain-text fallback
    parse_modes = [c.get("parse_mode") for c in sent]
    assert "HTML" in parse_modes
    assert None in parse_modes


def test_deliver_writes_file_when_all_telegram_attempts_fail(tmp_path: Path) -> None:
    md = "# T\n\n## S\nbody"
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=BadRequest("nope"))
    bot.__aenter__ = AsyncMock(return_value=bot)
    bot.__aexit__ = AsyncMock(return_value=None)

    def _fake_run(coro):
        coro.close()  # silence "coroutine never awaited"
        raise RuntimeError("boom")

    with patch("jmnews.delivery.telegram.Bot", return_value=bot), patch(
        "jmnews.delivery.telegram.asyncio.run", side_effect=_fake_run
    ):
        delivery = TelegramDelivery(_settings(tmp_path))
        status = delivery.deliver(_briefing(md))

    assert status == "file"
    assert (tmp_path / "briefings" / "2026-05-16.md").exists()


def test_async_send_handles_link_section(tmp_path: Path) -> None:
    """Smoke test that the full async path runs once end-to-end."""
    md = "## A\n- **Headline** - body. [src](https://e.com)"
    captured: list[str] = []

    class _FakeBot:
        def __init__(self, token: str) -> None: ...
        async def __aenter__(self):  # noqa: D401
            return self

        async def __aexit__(self, *a):
            return None

        async def send_message(self, **kwargs):  # noqa: ANN003
            captured.append(kwargs["text"])

    with patch("jmnews.delivery.telegram.Bot", _FakeBot):
        delivery = TelegramDelivery(_settings(tmp_path))
        asyncio.run(delivery._send_all(_split_into_sections(md)))

    assert any('<a href="https://e.com">src</a>' in c for c in captured)
    assert any("<b>Headline</b>" in c for c in captured)
