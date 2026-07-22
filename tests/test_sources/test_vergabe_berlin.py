"""Tests for the Berlin Vergabeplattform scraper and Gewaltschutz topic feed."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jmnews.sources import enabled_sources
from jmnews.sources.berlin_gewaltschutz import (
    SEARCH_TERMS,
    BerlinGewaltschutz,
    build_search_feed_url,
)
from jmnews.sources.vergabe_berlin import VergabeBerlin

OLD = datetime(2020, 1, 1, tzinfo=UTC)


# --- vergabe_berlin ---------------------------------------------------------


def _single_page(raw: str) -> VergabeBerlin:
    src = VergabeBerlin()
    src.max_pages = 1
    src.request_delay = 0  # no sleeping in tests
    return src


def test_keeps_social_tenders_filters_construction(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.html").read_text(encoding="utf-8")
    src = _single_page(raw)

    with patch("jmnews.sources.vergabe_berlin.http_get", return_value=raw):
        items = src.fetch(OLD)

    titles = [i.title for i in items]
    # Frauenhaus + Hilfen zur Erziehung survive, the construction tender is dropped.
    assert any("Frauen- und Kinderschutzhaus" in t for t in titles)
    assert any("Hilfen zur Erziehung" in t for t in titles)
    assert not any("Haufwerksbeprobungen" in t for t in titles)
    assert all(i.source == "vergabe_berlin" for i in items)


def test_extracts_url_date_and_snippet(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.html").read_text(encoding="utf-8")
    src = _single_page(raw)

    with patch("jmnews.sources.vergabe_berlin.http_get", return_value=raw):
        items = src.fetch(OLD)

    fh = next(i for i in items if "Frauen- und Kinderschutzhaus" in i.title)
    assert fh.url == (
        "https://meinauftrag.rib.de/public/DetailsByPlatformIdAndTenderId/"
        "platformId/2/tenderId/209001"
    )
    assert fh.published_at.date().isoformat() == "2026-07-20"
    assert "Interessenbekundungsverfahren" in fh.snippet
    assert "Frist: 15.09.2026" in fh.snippet


def test_filters_by_since(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.html").read_text(encoding="utf-8")
    src = _single_page(raw)
    since = datetime(2026, 7, 10, tzinfo=UTC)

    with patch("jmnews.sources.vergabe_berlin.http_get", return_value=raw):
        items = src.fetch(since)

    # The "Hilfen zur Erziehung" tender (05.07.) is out of window; Frauenhaus stays.
    titles = [i.title for i in items]
    assert any("Frauen- und Kinderschutzhaus" in t for t in titles)
    assert not any("Hilfen zur Erziehung" in t for t in titles)


def test_returns_empty_on_http_failure() -> None:
    src = VergabeBerlin()
    src.request_delay = 0
    with patch("jmnews.sources.vergabe_berlin.http_get", side_effect=RuntimeError("503")):
        assert src.fetch(OLD) == []


def test_stops_paginating_on_empty_page() -> None:
    src = VergabeBerlin()
    src.request_delay = 0
    empty = "<html><body><main></main></body></html>"
    with patch("jmnews.sources.vergabe_berlin.http_get", return_value=empty) as mock_get:
        items = src.fetch(OLD)
    assert items == []
    # First page empty => no further pagination requests.
    assert mock_get.call_count == 1


def test_dedupes_repeated_cards_across_pages(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.html").read_text(encoding="utf-8")
    src = VergabeBerlin()
    src.max_pages = 3
    src.request_delay = 0
    # Every page returns the same HTML: dedup by id, then stop when a page is
    # all-duplicates (page 2).
    with patch("jmnews.sources.vergabe_berlin.http_get", return_value=raw) as mock_get:
        items = src.fetch(OLD)
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))
    assert mock_get.call_count == 2


# --- berlin_gewaltschutz ----------------------------------------------------


def test_gewaltschutz_feed_urls_one_per_term() -> None:
    src = BerlinGewaltschutz()
    urls = src.feed_urls()
    assert len(urls) == len(SEARCH_TERMS)
    assert all("searchtext=" in u for u in urls)


def test_gewaltschutz_feed_url_encodes_term() -> None:
    assert build_search_feed_url("Frauenhaus").endswith("?searchtext=Frauenhaus")


def test_gewaltschutz_request_delay_against_429() -> None:
    assert BerlinGewaltschutz.request_delay > 0


def test_gewaltschutz_not_in_alarm_sources() -> None:
    # Plain Frauenhaus news must not blanket-trigger the Trägeraufruf alarm.
    from jmnews.briefing import _TRAEGERAUFRUF_SOURCES

    assert "berlin_gewaltschutz" not in _TRAEGERAUFRUF_SOURCES


def test_new_sources_registered() -> None:
    names = {s.name for s in enabled_sources()}
    assert "vergabe_berlin" in names
    assert "berlin_gewaltschutz" in names
