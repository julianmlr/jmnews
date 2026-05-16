"""SQLite-backed storage for items, briefings, runs."""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from jmnews.models import Briefing, Category, FilterResult, NewsItem, Run

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    snippet TEXT NOT NULL DEFAULT '',
    raw_html TEXT,
    score INTEGER,
    category TEXT,
    reasoning TEXT,
    fetched_at TEXT NOT NULL,
    delivered_in_briefing_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
CREATE INDEX IF NOT EXISTS idx_items_briefing ON items(delivered_in_briefing_id);

CREATE TABLE IF NOT EXISTS briefings (
    id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    markdown TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    delivered_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT
);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class Storage:
    """Thin SQLite wrapper. One instance per process, thread-safe enough for our use."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Any:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ---------- items ----------

    def upsert_item(self, item: NewsItem) -> bool:
        """Insert item if new. Returns True if inserted, False if duplicate."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO items
                    (id, source, title, url, published_at, snippet, raw_html,
                     score, category, reasoning, fetched_at, delivered_in_briefing_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.source,
                    item.title,
                    item.url,
                    _iso(item.published_at),
                    item.snippet,
                    item.raw_html,
                    item.score,
                    item.category,
                    item.reasoning,
                    _iso(item.fetched_at),
                    item.delivered_in_briefing_id,
                ),
            )
            return cur.rowcount == 1

    def upsert_items(self, items: Iterable[NewsItem]) -> int:
        inserted = 0
        for item in items:
            if self.upsert_item(item):
                inserted += 1
        return inserted

    def get_item(self, item_id: str) -> NewsItem | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return _row_to_item(row) if row else None

    def get_unfiltered_items_since(self, since: datetime) -> list[NewsItem]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM items
                WHERE category IS NULL AND published_at >= ?
                ORDER BY published_at DESC
                """,
                (_iso(since),),
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    def get_items_for_briefing(self, since: datetime) -> list[NewsItem]:
        """Items classified as relevant/action, not yet delivered, within window."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM items
                WHERE category IN ('relevant', 'action', 'context')
                  AND delivered_in_briefing_id IS NULL
                  AND published_at >= ?
                ORDER BY score DESC, published_at DESC
                """,
                (_iso(since),),
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    def count_items_by_category(self, since: datetime) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(category, 'unfiltered') AS cat, COUNT(*) AS n
                FROM items
                WHERE published_at >= ?
                GROUP BY cat
                """,
                (_iso(since),),
            ).fetchall()
        return {r["cat"]: r["n"] for r in rows}

    def apply_filter_result(self, result: FilterResult) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE items
                SET score = ?, category = ?, reasoning = ?
                WHERE id = ?
                """,
                (result.score, result.category, result.reasoning, result.id),
            )

    def mark_delivered(self, item_ids: Iterable[str], briefing_id: str) -> None:
        ids = list(item_ids)
        if not ids:
            return
        with self._conn() as conn:
            conn.executemany(
                "UPDATE items SET delivered_in_briefing_id = ? WHERE id = ?",
                [(briefing_id, i) for i in ids],
            )

    def purge_old(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM items WHERE published_at < ?", (_iso(cutoff),)
            )
            n = cur.rowcount
        if n:
            logger.info("Purged {} items older than {} days", n, days)
        return n

    # ---------- briefings ----------

    def save_briefing(self, briefing: Briefing) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO briefings
                    (id, generated_at, markdown, item_count, delivered_at, delivery_status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    briefing.id,
                    _iso(briefing.generated_at),
                    briefing.markdown,
                    briefing.item_count,
                    _iso(briefing.delivered_at) if briefing.delivered_at else None,
                    briefing.delivery_status,
                ),
            )

    def get_briefing(self, briefing_id: str) -> Briefing | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM briefings WHERE id = ?", (briefing_id,)
            ).fetchone()
        return _row_to_briefing(row) if row else None

    # ---------- runs ----------

    def start_run(self, kind: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, kind, started_at, status)
                VALUES (?, ?, ?, 'running')
                """,
                (run_id, kind, _iso(datetime.now(UTC))),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE runs SET finished_at = ?, status = ?, error = ?
                WHERE id = ?
                """,
                (_iso(datetime.now(UTC)), status, error, run_id),
            )

    def get_run(self, run_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row else None

    # ---------- backup ----------

    def backup(self) -> Path:
        bak = self.db_path.with_suffix(self.db_path.suffix + ".bak")
        if self.db_path.exists():
            shutil.copy2(self.db_path, bak)
            logger.info("DB backed up to {}", bak)
        return bak


def _row_to_item(row: sqlite3.Row) -> NewsItem:
    return NewsItem(
        id=row["id"],
        source=row["source"],
        title=row["title"],
        url=row["url"],
        published_at=_parse_dt(row["published_at"]),  # type: ignore[arg-type]
        snippet=row["snippet"] or "",
        raw_html=row["raw_html"],
        score=row["score"],
        category=row["category"] if row["category"] else None,  # type: ignore[arg-type]
        reasoning=row["reasoning"],
        fetched_at=_parse_dt(row["fetched_at"]),  # type: ignore[arg-type]
        delivered_in_briefing_id=row["delivered_in_briefing_id"],
    )


def _row_to_briefing(row: sqlite3.Row) -> Briefing:
    delivered_at = _parse_dt(row["delivered_at"])
    return Briefing(
        id=row["id"],
        generated_at=_parse_dt(row["generated_at"]),  # type: ignore[arg-type]
        markdown=row["markdown"],
        item_count=row["item_count"],
        delivered_at=delivered_at,
        delivery_status=row["delivery_status"],
    )


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        kind=row["kind"],
        started_at=_parse_dt(row["started_at"]),  # type: ignore[arg-type]
        finished_at=_parse_dt(row["finished_at"]),
        status=row["status"],
        error=row["error"],
    )


# Re-export for convenience
__all__ = ["Storage", "Category"]
