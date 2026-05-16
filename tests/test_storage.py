"""Tests for jmnews.storage."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jmnews.models import Briefing, FilterResult, NewsItem, stable_id
from jmnews.storage import Storage


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "test.db")


def _make_item(
    url: str = "https://example.com/a",
    source: str = "test",
    published_at: datetime | None = None,
    title: str = "Hello",
) -> NewsItem:
    return NewsItem(
        id=stable_id(url),
        source=source,
        title=title,
        url=url,
        published_at=published_at or datetime.now(UTC),
        snippet="snippet",
    )


def test_upsert_item_inserts_once(storage: Storage) -> None:
    item = _make_item()
    assert storage.upsert_item(item) is True
    assert storage.upsert_item(item) is False  # dedup
    assert storage.get_item(item.id) is not None


def test_upsert_items_counts_new(storage: Storage) -> None:
    items = [
        _make_item("https://example.com/1"),
        _make_item("https://example.com/2"),
        _make_item("https://example.com/1"),  # dup
    ]
    assert storage.upsert_items(items) == 2


def test_get_unfiltered_items_since(storage: Storage) -> None:
    now = datetime.now(UTC)
    storage.upsert_item(_make_item("https://e.com/recent", published_at=now))
    storage.upsert_item(
        _make_item("https://e.com/old", published_at=now - timedelta(days=5))
    )
    recent = storage.get_unfiltered_items_since(now - timedelta(hours=24))
    assert len(recent) == 1
    assert recent[0].url == "https://e.com/recent"


def test_apply_filter_result_updates_category(storage: Storage) -> None:
    item = _make_item("https://e.com/x")
    storage.upsert_item(item)
    storage.apply_filter_result(
        FilterResult(id=item.id, score=9, category="action", reasoning="Frist morgen")
    )
    loaded = storage.get_item(item.id)
    assert loaded is not None
    assert loaded.category == "action"
    assert loaded.score == 9
    assert loaded.reasoning == "Frist morgen"


def test_get_items_for_briefing_filters_correctly(storage: Storage) -> None:
    now = datetime.now(UTC)
    a = _make_item("https://e.com/a", published_at=now)
    b = _make_item("https://e.com/b", published_at=now)
    c = _make_item("https://e.com/c", published_at=now)
    storage.upsert_items([a, b, c])
    storage.apply_filter_result(FilterResult(id=a.id, score=9, category="action"))
    storage.apply_filter_result(FilterResult(id=b.id, score=7, category="relevant"))
    storage.apply_filter_result(FilterResult(id=c.id, score=1, category="ignore"))

    items = storage.get_items_for_briefing(now - timedelta(hours=24))
    ids = [i.id for i in items]
    assert a.id in ids
    assert b.id in ids
    assert c.id not in ids
    # action ranks first
    assert items[0].id == a.id


def test_mark_delivered_excludes_from_next_briefing(storage: Storage) -> None:
    now = datetime.now(UTC)
    item = _make_item("https://e.com/a", published_at=now)
    storage.upsert_item(item)
    storage.apply_filter_result(FilterResult(id=item.id, score=9, category="action"))
    storage.mark_delivered([item.id], briefing_id="2026-05-16")
    assert storage.get_items_for_briefing(now - timedelta(hours=24)) == []


def test_purge_old_removes_outdated(storage: Storage) -> None:
    now = datetime.now(UTC)
    storage.upsert_item(_make_item("https://e.com/old", published_at=now - timedelta(days=40)))
    storage.upsert_item(_make_item("https://e.com/new", published_at=now))
    purged = storage.purge_old(days=30)
    assert purged == 1
    assert storage.get_item(stable_id("https://e.com/old")) is None
    assert storage.get_item(stable_id("https://e.com/new")) is not None


def test_save_and_get_briefing(storage: Storage) -> None:
    briefing = Briefing(
        id="2026-05-16",
        generated_at=datetime.now(UTC),
        markdown="# Test",
        item_count=3,
    )
    storage.save_briefing(briefing)
    loaded = storage.get_briefing("2026-05-16")
    assert loaded is not None
    assert loaded.markdown == "# Test"
    assert loaded.delivery_status == "pending"


def test_run_lifecycle(storage: Storage) -> None:
    run_id = storage.start_run("collect")
    run = storage.get_run(run_id)
    assert run is not None
    assert run.status == "running"
    storage.finish_run(run_id, "success")
    run = storage.get_run(run_id)
    assert run is not None
    assert run.status == "success"
    assert run.finished_at is not None


def test_backup_copies_db_file(storage: Storage) -> None:
    storage.upsert_item(_make_item())
    bak = storage.backup()
    assert bak.exists()
    assert bak.read_bytes() == storage.db_path.read_bytes()


def test_count_items_by_category(storage: Storage) -> None:
    now = datetime.now(UTC)
    a = _make_item("https://e.com/a", published_at=now)
    b = _make_item("https://e.com/b", published_at=now)
    storage.upsert_items([a, b])
    storage.apply_filter_result(FilterResult(id=a.id, score=9, category="action"))
    counts = storage.count_items_by_category(now - timedelta(hours=24))
    assert counts.get("action") == 1
    assert counts.get("unfiltered") == 1
