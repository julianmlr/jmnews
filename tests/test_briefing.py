"""Tests for jmnews.briefing."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from jmnews.briefing import BriefingGenerator, _group_items, _render_fallback
from jmnews.config import Settings
from jmnews.models import Category, NewsItem, stable_id


def _item(
    url: str,
    *,
    category: Category | None = None,
    score: int | None = None,
    title: str = "Titel",
) -> NewsItem:
    return NewsItem(
        id=stable_id(url),
        source="berlin_presseportal",
        title=title,
        url=url,
        published_at=datetime.now(UTC),
        snippet="snippet",
        category=category,
        score=score,
    )


def _settings(tmp_path: Path) -> Settings:
    profile = tmp_path / "jm_profile.md"
    profile.write_text("JM profile stub", encoding="utf-8")
    return Settings(ANTHROPIC_API_KEY="sk-ant-test", JMNEWS_PROFILE_PATH=profile)


def _fake_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_group_items_sorts_and_limits() -> None:
    items = [
        _item(f"https://e.com/a{i}", category="action", score=i) for i in range(7)
    ] + [
        _item(f"https://e.com/r{i}", category="relevant", score=i) for i in range(10)
    ] + [
        _item(f"https://e.com/c{i}", category="context", score=i) for i in range(15)
    ] + [
        _item("https://e.com/ign", category="ignore", score=0),
    ]
    groups = _group_items(items)
    assert len(groups["action"]) == 5
    assert len(groups["relevant"]) == 8
    assert len(groups["context"]) == 10
    # highest score first
    assert groups["action"][0].score == 6
    assert groups["relevant"][0].score == 9


def test_generate_calls_sonnet_and_returns_briefing(tmp_path: Path) -> None:
    a = _item("https://e.com/a", category="action", score=9, title="Frist")
    b = _item("https://e.com/b", category="relevant", score=7)
    c = _item("https://e.com/c", category="ignore", score=0)

    client = MagicMock()
    client.messages.create.return_value = _fake_response("# JM-Briefing 2026-05-16\nBody")

    gen = BriefingGenerator(_settings(tmp_path), client=client)
    briefing = gen.generate([a, b, c], briefing_date=date(2026, 5, 16))

    assert briefing.id == "2026-05-16"
    assert briefing.markdown.startswith("# JM-Briefing")
    assert briefing.item_count == 2  # a + b; c is ignored
    kwargs = client.messages.create.call_args.kwargs
    # First system block is the JM profile and must be cached
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    # User prompt contains the action item
    user_prompt = kwargs["messages"][0]["content"]
    assert "ACTION" in user_prompt
    assert "Frist" in user_prompt
    assert "Ignorierte Items heute: 1" in user_prompt


def test_generate_falls_back_when_sonnet_fails(tmp_path: Path, monkeypatch) -> None:
    import anthropic as anth

    monkeypatch.setattr("jmnews.briefing.time.sleep", lambda _s: None)
    a = _item("https://e.com/a", category="action", score=9, title="Frist")

    client = MagicMock()
    err = anth.APIConnectionError(request=MagicMock())
    client.messages.create.side_effect = [err, err, err]

    gen = BriefingGenerator(_settings(tmp_path), client=client)
    briefing = gen.generate([a], briefing_date=date(2026, 5, 16))

    assert "LLM-Generierung fehlgeschlagen" in briefing.markdown
    assert "Frist" in briefing.markdown
    assert briefing.item_count == 1
    assert client.messages.create.call_count == 3


def test_render_fallback_omits_empty_sections() -> None:
    a = _item("https://e.com/a", category="action", score=9, title="Hot")
    md = _render_fallback(
        {"action": [a], "relevant": [], "context": []},
        ignored=3,
        briefing_date=date(2026, 5, 16),
    )
    assert "🚨 DRINGEND" in md
    assert "🔥 HOCH" not in md
    assert "📰 HINTERGRUND" not in md
    assert "Übersprungen heute" in md
    assert "3 Items als ignore" in md


def test_generate_handles_no_items(tmp_path: Path) -> None:
    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        "# JM-Briefing 2026-05-16\nKeine relevanten Nachrichten heute."
    )

    gen = BriefingGenerator(_settings(tmp_path), client=client)
    briefing = gen.generate([], briefing_date=date(2026, 5, 16))

    assert briefing.item_count == 0
    assert briefing.markdown.startswith("# JM-Briefing")
