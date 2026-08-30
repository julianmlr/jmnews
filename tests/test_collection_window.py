"""Regression tests for the collection window.

Date-only sources (nexxt-change, Insolvenzportal, Vergabeplattformen) parse to
midnight. A plain rolling `now - lookback` cut dropped a whole day of those
items; these tests pin the midnight-floored window that fixes it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jmnews.pipeline import collection_window_start


def test_floors_to_midnight() -> None:
    now = datetime(2026, 8, 30, 6, 45, tzinfo=UTC)
    assert collection_window_start(24, now=now) == datetime(2026, 8, 29, 0, 0, tzinfo=UTC)


def test_catches_ad_posted_after_yesterdays_run() -> None:
    """The nexxt-change case: ad dated 28.08 went online after the 06:45 run."""
    published = datetime(2026, 8, 28, 0, 0, tzinfo=UTC)  # date-only → midnight

    # Run on the 29th: previously since=28.08 06:45 excluded it. Now included.
    since_29 = collection_window_start(24, now=datetime(2026, 8, 29, 6, 45, tzinfo=UTC))
    assert published >= since_29

    old_style = datetime(2026, 8, 29, 6, 45, tzinfo=UTC) - timedelta(hours=24)
    assert published < old_style  # the bug this fixes


def test_no_blind_window_for_any_posting_time() -> None:
    """Whatever hour of day X something is posted, the day X+1 run sees it."""
    run_hour = 6  # daily 06:45 briefing
    for day in (10, 20, 28):
        published = datetime(2026, 8, day, 0, 0, tzinfo=UTC)  # date-only
        next_run = datetime(2026, 8, day + 1, run_hour, 45, tzinfo=UTC)
        assert published >= collection_window_start(24, now=next_run)


def test_window_never_extends_beyond_two_days() -> None:
    """Flooring widens the window, but boundedly — no unbounded backfill."""
    now = datetime(2026, 8, 30, 23, 59, tzinfo=UTC)
    since = collection_window_start(24, now=now)
    assert timedelta(hours=24) <= now - since < timedelta(hours=48)


def test_respects_configured_lookback() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    assert collection_window_start(72, now=now) == datetime(2026, 8, 27, 0, 0, tzinfo=UTC)
