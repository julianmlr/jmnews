"""Tests for the read-only HTTP API."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from jmnews.api import make_server, run_in_thread
from jmnews.config import Settings
from jmnews.models import Briefing, FilterResult, NewsItem, stable_id
from jmnews.storage import Storage

TOKEN = "test-token-123"


def _item(url: str, title: str, published_at: datetime | None = None) -> NewsItem:
    return NewsItem(
        id=stable_id(url),
        source="test",
        title=title,
        url=url,
        published_at=published_at or datetime.now(UTC),
        snippet="snippet",
    )


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    st = Storage(tmp_path / "test.db")
    a = _item("https://e.com/a", "Aktion Kita-Frist")
    b = _item("https://e.com/b", "Relevant Vergabe")
    c = _item("https://e.com/c", "Ignoriert Sport")
    old = _item("https://e.com/old", "Alt", datetime.now(UTC) - timedelta(days=10))
    st.upsert_items([a, b, c, old])
    st.apply_filter_result(FilterResult(id=a.id, score=9, category="action", reasoning="Frist"))
    st.apply_filter_result(FilterResult(id=b.id, score=6, category="relevant", reasoning="ok"))
    st.apply_filter_result(FilterResult(id=c.id, score=1, category="ignore", reasoning="Sport"))
    st.apply_filter_result(FilterResult(id=old.id, score=8, category="action", reasoning="alt"))
    st.save_briefing(
        Briefing(
            id="2026-09-10",
            generated_at=datetime.now(UTC) - timedelta(days=1),
            markdown="# Gestern",
            item_count=1,
            delivery_status="telegram",
        )
    )
    st.save_briefing(
        Briefing(
            id="2026-09-11",
            generated_at=datetime.now(UTC),
            markdown="# JM-Briefing 2026-09-11\n\n## 🔥 Aktion\n- Kita-Frist",
            item_count=2,
            delivered_at=datetime.now(UTC),
            delivery_status="telegram",
        )
    )
    st.mark_delivered([a.id, b.id], "2026-09-11")
    st.mark_delivered([old.id], "2026-09-10")
    return st


@pytest.fixture
def client(storage: Storage, tmp_path: Path) -> Iterator[httpx.Client]:
    settings = Settings(
        JMNEWS_DB_PATH=storage.db_path,
        JMNEWS_API_HOST="127.0.0.1",
        JMNEWS_API_PORT=0,  # ephemeral
        JMNEWS_API_TOKEN=TOKEN,
    )
    server = make_server(settings, storage)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    port = server.server_address[1]
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": f"Bearer {TOKEN}"}
    ) as c:
        yield c
    server.shutdown()
    server.server_close()


def test_health_needs_no_auth(client: httpx.Client) -> None:
    r = client.get("/health", headers={"Authorization": ""})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_rejects_missing_or_wrong_token(client: httpx.Client) -> None:
    assert client.get("/api/briefings/latest", headers={"Authorization": ""}).status_code == 401
    assert (
        client.get("/api/briefings/latest", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )


def test_accepts_x_api_key_header(client: httpx.Client) -> None:
    r = client.get("/api/briefings/latest", headers={"Authorization": "", "X-API-Key": TOKEN})
    assert r.status_code == 200


def test_latest_briefing_includes_markdown_and_items(client: httpx.Client) -> None:
    r = client.get("/api/briefings/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "2026-09-11"
    assert data["delivery_status"] == "telegram"
    assert "Kita-Frist" in data["markdown"]
    titles = [i["title"] for i in data["items"]]
    assert titles == ["Aktion Kita-Frist", "Relevant Vergabe"]  # score desc
    assert data["items"][0]["category"] == "action"
    assert data["items"][0]["url"] == "https://e.com/a"


def test_briefing_by_date(client: httpx.Client) -> None:
    r = client.get("/api/briefings/2026-09-10")
    assert r.status_code == 200
    data = r.json()
    assert data["markdown"] == "# Gestern"
    assert [i["title"] for i in data["items"]] == ["Alt"]


def test_briefing_not_found_and_bad_id(client: httpx.Client) -> None:
    assert client.get("/api/briefings/2020-01-01").status_code == 404
    assert client.get("/api/briefings/not-a-date").status_code == 400


def test_list_briefings_newest_first_without_markdown(client: httpx.Client) -> None:
    r = client.get("/api/briefings", params={"limit": 1})
    assert r.status_code == 200
    briefings = r.json()["briefings"]
    assert [b["id"] for b in briefings] == ["2026-09-11"]
    assert "markdown" not in briefings[0]
    assert len(client.get("/api/briefings").json()["briefings"]) == 2


def test_items_filters(client: httpx.Client) -> None:
    r = client.get("/api/items", params={"since_days": 1})
    assert r.status_code == 200
    assert r.json()["count"] == 3  # old one is outside window

    r = client.get("/api/items", params={"since_days": 1, "category": "action,relevant"})
    assert [i["title"] for i in r.json()["items"]] == ["Aktion Kita-Frist", "Relevant Vergabe"]

    r = client.get("/api/items", params={"since_days": 30, "category": "action"})
    assert r.json()["count"] == 2

    assert client.get("/api/items", params={"since_days": "x"}).status_code == 400
    assert client.get("/api/items", params={"limit": 0}).status_code == 400


def test_unknown_endpoint_is_404(client: httpx.Client) -> None:
    assert client.get("/api/nope").status_code == 404


def test_run_in_thread_is_noop_without_token(storage: Storage) -> None:
    settings = Settings(JMNEWS_DB_PATH=storage.db_path, JMNEWS_API_TOKEN="")
    assert run_in_thread(settings, storage) is None
    settings = Settings(
        JMNEWS_DB_PATH=storage.db_path, JMNEWS_API_TOKEN="x", JMNEWS_API_ENABLED=False
    )
    assert run_in_thread(settings, storage) is None
