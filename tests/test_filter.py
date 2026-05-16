"""Tests for jmnews.filter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jmnews.config import Settings
from jmnews.filter import Filter, _parse_response
from jmnews.models import NewsItem, stable_id


def _item(url: str, title: str = "Titel", snippet: str = "Snippet") -> NewsItem:
    return NewsItem(
        id=stable_id(url),
        source="berlin_presseportal",
        title=title,
        url=url,
        published_at=datetime.now(UTC),
        snippet=snippet,
    )


def _settings(tmp_path: Path) -> Settings:
    profile = tmp_path / "jm_profile.md"
    profile.write_text("JM Profil Stub", encoding="utf-8")
    return Settings(
        ANTHROPIC_API_KEY="sk-ant-test",
        JMNEWS_PROFILE_PATH=profile,
        JMNEWS_FILTER_BATCH_SIZE=2,
    )


def _fake_response(payload: list[dict]) -> SimpleNamespace:
    text_block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[text_block])


def test_parse_response_extracts_array() -> None:
    item = _item("https://e.com/a")
    text = json.dumps(
        [{"id": item.id, "score": 8, "category": "relevant", "reasoning": "passt"}]
    )
    out = _parse_response(text, [item])
    assert len(out) == 1
    assert out[0].id == item.id
    assert out[0].category == "relevant"


def test_parse_response_strips_code_fence() -> None:
    item = _item("https://e.com/a")
    text = (
        "```json\n"
        + json.dumps(
            [{"id": item.id, "score": 3, "category": "context", "reasoning": "Kontext"}]
        )
        + "\n```"
    )
    out = _parse_response(text, [item])
    assert out[0].category == "context"


def test_parse_response_ignores_unknown_ids() -> None:
    item = _item("https://e.com/a")
    text = json.dumps(
        [{"id": "unknown", "score": 8, "category": "relevant", "reasoning": "x"}]
    )
    assert _parse_response(text, [item]) == []


def test_parse_response_rejects_invalid_category() -> None:
    item = _item("https://e.com/a")
    text = json.dumps([{"id": item.id, "score": 5, "category": "maybe"}])
    assert _parse_response(text, [item]) == []


def test_parse_response_handles_garbage() -> None:
    item = _item("https://e.com/a")
    assert _parse_response("nope, not json", [item]) == []


def test_filter_classifies_items(tmp_path: Path) -> None:
    a = _item("https://e.com/a", title="Frist Kita-Antrag")
    b = _item("https://e.com/b", title="Bundesliga Spieltag")
    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        [
            {"id": a.id, "score": 9, "category": "action", "reasoning": "Frist morgen"},
            {"id": b.id, "score": 1, "category": "ignore", "reasoning": "Sport"},
        ]
    )

    f = Filter(_settings(tmp_path), client=client)
    results = f.classify([a, b])

    assert {r.id for r in results} == {a.id, b.id}
    by_id = {r.id: r for r in results}
    assert by_id[a.id].category == "action"
    assert by_id[b.id].category == "ignore"
    client.messages.create.assert_called_once()
    kwargs = client.messages.create.call_args.kwargs
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_filter_batches_by_size(tmp_path: Path) -> None:
    items = [_item(f"https://e.com/{i}") for i in range(5)]
    client = MagicMock()

    def respond(**kwargs):  # noqa: ANN003
        sent = json.loads(kwargs["messages"][0]["content"].split("Items:\n", 1)[1])
        return _fake_response(
            [
                {"id": s["id"], "score": 5, "category": "context", "reasoning": "ok"}
                for s in sent
            ]
        )

    client.messages.create.side_effect = respond

    settings = _settings(tmp_path)
    settings.filter_batch_size = 2
    f = Filter(settings, client=client)
    out = f.classify(items)

    assert len(out) == 5
    assert client.messages.create.call_count == 3  # 2 + 2 + 1


def test_filter_retries_on_api_error(tmp_path: Path, monkeypatch) -> None:
    import anthropic as anth

    monkeypatch.setattr("jmnews.filter.time.sleep", lambda _s: None)
    a = _item("https://e.com/a")
    client = MagicMock()
    err = anth.APIConnectionError(request=MagicMock())
    client.messages.create.side_effect = [
        err,
        err,
        _fake_response(
            [{"id": a.id, "score": 7, "category": "relevant", "reasoning": "ok"}]
        ),
    ]

    f = Filter(_settings(tmp_path), client=client)
    out = f.classify([a])

    assert client.messages.create.call_count == 3
    assert len(out) == 1
    assert out[0].category == "relevant"


def test_filter_returns_empty_after_max_retries(tmp_path: Path, monkeypatch) -> None:
    import anthropic as anth

    monkeypatch.setattr("jmnews.filter.time.sleep", lambda _s: None)
    a = _item("https://e.com/a")
    client = MagicMock()
    err = anth.APIConnectionError(request=MagicMock())
    client.messages.create.side_effect = [err, err, err]

    f = Filter(_settings(tmp_path), client=client)
    out = f.classify([a])

    assert out == []
    assert client.messages.create.call_count == 3


def test_filter_requires_api_key_or_client() -> None:
    settings = Settings(ANTHROPIC_API_KEY="", JMNEWS_PROFILE_PATH=Path("jm_profile.md"))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        Filter(settings)
