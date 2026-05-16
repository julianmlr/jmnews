"""Tests for the Tagesspiegel Google-News-Sitemap parser."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jmnews.sources.tagesspiegel import Tagesspiegel


def test_parses_only_berlin_section_items(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "tagesspiegel_sitemap.xml").read_text(encoding="utf-8")
    src = Tagesspiegel()
    since = datetime(2026, 5, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(since)

    titles = [i.title for i in items]
    assert "Verlängerung der U7 in Spandau" in titles
    assert "High Fiber Drinks im Supermarktregal" in titles
    # non-Berlin section is filtered out
    assert "Eurovision Song Contest 2026" not in titles
    assert all("/berlin/" in i.url for i in items)
    assert all(i.source == "tagesspiegel" for i in items)


def test_filters_by_since(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "tagesspiegel_sitemap.xml").read_text(encoding="utf-8")
    src = Tagesspiegel()
    since = datetime(2026, 5, 16, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(since)

    titles = [i.title for i in items]
    assert "Verlängerung der U7 in Spandau" in titles
    assert "High Fiber Drinks im Supermarktregal" not in titles
    assert "Altes Berlin-Item" not in titles


def test_returns_empty_on_http_failure() -> None:
    src = Tagesspiegel()
    since = datetime(2026, 1, 1, tzinfo=UTC)
    with patch("jmnews.sources.base.http_get", side_effect=RuntimeError("503")):
        assert src.fetch(since) == []


def test_returns_empty_on_bad_xml() -> None:
    src = Tagesspiegel()
    since = datetime(2026, 1, 1, tzinfo=UTC)
    with patch("jmnews.sources.base.http_get", return_value="not xml"):
        assert src.fetch(since) == []


def test_default_url_points_to_news_sitemap() -> None:
    assert Tagesspiegel.DEFAULT_URL.endswith("/news.xml")
