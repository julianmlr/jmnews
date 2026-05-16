"""Tests for the APScheduler daemon."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jmnews.config import Settings
from jmnews.pipeline import _safe_run, run_daemon


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    profile = tmp_path / "jm_profile.md"
    profile.write_text("stub", encoding="utf-8")
    return Settings(
        JMNEWS_DB_PATH=tmp_path / "test.db",
        JMNEWS_PROFILE_PATH=profile,
        JMNEWS_BRIEFINGS_DIR=tmp_path / "briefings",
        JMNEWS_LOG_DIR=tmp_path / "logs",
        JMNEWS_COLLECT_HOUR=6,
        JMNEWS_COLLECT_MINUTE=45,
        JMNEWS_TIMEZONE="Europe/Berlin",
    )


def test_run_daemon_schedules_daily_job_and_starts(settings: Settings) -> None:
    sched = MagicMock()
    with patch("jmnews.pipeline.BlockingScheduler", return_value=sched):
        run_daemon(settings)

    sched.add_job.assert_called_once()
    sched.start.assert_called_once()
    kwargs = sched.add_job.call_args.kwargs
    trigger = kwargs["trigger"]
    # CronTrigger has a __str__ that shows fields; assert configured time
    assert "hour='6'" in str(trigger)
    assert "minute='45'" in str(trigger)
    assert kwargs["id"] == "daily_briefing"
    assert kwargs["coalesce"] is True


def test_safe_run_swallows_exceptions(settings: Settings) -> None:
    with patch("jmnews.pipeline.run_once", side_effect=RuntimeError("boom")):
        # Should not raise
        _safe_run(settings)


def test_safe_run_delegates_to_run_once(settings: Settings) -> None:
    with patch("jmnews.pipeline.run_once") as run_once_mock:
        _safe_run(settings)
        run_once_mock.assert_called_once_with(settings)
