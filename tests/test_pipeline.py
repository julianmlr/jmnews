"""End-to-end pipeline test with mocked sources, filter, briefing, delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from jmnews.config import Settings
from jmnews.models import Briefing, FilterResult, NewsItem, stable_id
from jmnews.pipeline import run_once
from jmnews.sources.base import Source


class _StaticSource(Source):
    name = "static_test"

    def __init__(self, items: list[NewsItem]) -> None:
        self._items = items

    def fetch(self, since: datetime) -> list[NewsItem]:  # noqa: ARG002
        return self._items


def _item(url: str, title: str = "Titel") -> NewsItem:
    return NewsItem(
        id=stable_id(url),
        source="static_test",
        title=title,
        url=url,
        published_at=datetime.now(UTC),
        snippet="snippet",
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    profile = tmp_path / "jm_profile.md"
    profile.write_text("JM Profil Stub", encoding="utf-8")
    return Settings(
        ANTHROPIC_API_KEY="sk-ant-test",
        JMNEWS_DB_PATH=tmp_path / "test.db",
        JMNEWS_PROFILE_PATH=profile,
        JMNEWS_BRIEFINGS_DIR=tmp_path / "briefings",
        JMNEWS_LOG_DIR=tmp_path / "logs",
        TELEGRAM_BOT_TOKEN="",  # forces file delivery
        TELEGRAM_CHAT_ID="",
        JMNEWS_LOOKBACK_HOURS=24,
    )


def test_run_once_end_to_end_with_mocked_externals(settings: Settings) -> None:
    a = _item("https://e.com/a", title="Kita-Frist morgen")
    b = _item("https://e.com/b", title="Bundesliga")

    with patch(
        "jmnews.pipeline.enabled_sources", return_value=[_StaticSource([a, b])]
    ), patch("jmnews.pipeline.Filter") as filter_cls, patch(
        "jmnews.pipeline.BriefingGenerator"
    ) as briefing_cls:
        filter_cls.return_value.classify.return_value = [
            FilterResult(id=a.id, score=9, category="action", reasoning="Frist"),
            FilterResult(id=b.id, score=1, category="ignore", reasoning="Sport"),
        ]
        briefing_cls.return_value.generate.return_value = Briefing(
            id="2026-05-16",
            generated_at=datetime.now(UTC),
            markdown="# JM-Briefing 2026-05-16\n\n## 🔥 Aktion\n- Kita-Frist",
            item_count=1,
        )

        summary = run_once(settings)

    assert summary.new_items == 2
    assert summary.filtered == 2
    assert summary.briefing_items == 1  # only action/relevant/context items
    assert summary.ignored_count == 1
    assert summary.delivery_status == "file"  # telegram not configured
    # briefing file written
    briefing_file = Path(settings.briefings_dir) / f"{summary.briefing_id}.md"
    assert briefing_file.exists()
    assert "Aktion" in briefing_file.read_text(encoding="utf-8")


def test_run_once_continues_when_source_fails(settings: Settings) -> None:
    class _BoomSource(Source):
        name = "boom"

        def fetch(self, since):  # noqa: ANN001, ARG002
            raise RuntimeError("network")

    a = _item("https://e.com/a")
    sources = [_BoomSource(), _StaticSource([a])]

    with patch("jmnews.pipeline.enabled_sources", return_value=sources), patch(
        "jmnews.pipeline.Filter"
    ) as filter_cls, patch("jmnews.pipeline.BriefingGenerator") as briefing_cls:
        filter_cls.return_value.classify.return_value = [
            FilterResult(id=a.id, score=7, category="relevant", reasoning="ok"),
        ]
        briefing_cls.return_value.generate.return_value = Briefing(
            id="2026-05-16",
            generated_at=datetime.now(UTC),
            markdown="# JM-Briefing",
            item_count=1,
        )
        summary = run_once(settings)

    assert summary.new_items == 1  # boom contributed nothing
    assert summary.filtered == 1


def test_run_once_marks_run_failed_on_unhandled_error(settings: Settings) -> None:
    with patch(
        "jmnews.pipeline.enabled_sources", side_effect=RuntimeError("nope")
    ), pytest.raises(RuntimeError, match="nope"):
        run_once(settings)

    # storage should record the failed run
    from jmnews.storage import Storage

    storage = Storage(settings.db_path)
    with storage._conn() as conn:
        row = conn.execute(
            "SELECT status, error FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    assert row["status"] == "failed"
    assert "nope" in (row["error"] or "")


def test_run_once_does_not_re_deliver_items(settings: Settings) -> None:
    a = _item("https://e.com/a")

    with patch(
        "jmnews.pipeline.enabled_sources", return_value=[_StaticSource([a])]
    ), patch("jmnews.pipeline.Filter") as filter_cls, patch(
        "jmnews.pipeline.BriefingGenerator"
    ) as briefing_cls:
        filter_cls.return_value.classify.return_value = [
            FilterResult(id=a.id, score=9, category="action", reasoning="ok"),
        ]
        # Mock returns whatever items it gets each time
        briefing_cls.return_value.generate.side_effect = lambda items, d, **kw: Briefing(
            id=d.isoformat(),
            generated_at=datetime.now(UTC),
            markdown=f"# {len(items)} items",
            item_count=len(items),
        )

        first = run_once(settings)
        second = run_once(settings)

    assert first.briefing_items == 1
    assert second.briefing_items == 0  # already delivered


def test_cli_version_command(tmp_path: Path) -> None:
    """Sanity check that the typer CLI loads."""
    from typer.testing import CliRunner

    from jmnews.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
