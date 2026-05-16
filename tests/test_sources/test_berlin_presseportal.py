"""Tests for the Berlin Presseportal aggregated RSS source."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from jmnews.sources.berlin_presseportal import (
    BASE_URL,
    DEFAULT_INSTITUTIONS,
    BerlinPresseportal,
    build_feed_url,
)


def test_build_feed_url_has_all_institutions() -> None:
    url = build_feed_url()
    assert url.startswith(f"{BASE_URL}?")
    # one `institutions[]=` per institution (server expects literal brackets per spec)
    assert url.count("institutions[]=") == len(DEFAULT_INSTITUTIONS)


def test_build_feed_url_encodes_umlauts_and_spaces() -> None:
    url = build_feed_url(("Senatsverwaltung für Finanzen",))
    # Spaces become + and umlauts get %-encoded
    assert "Senatsverwaltung+f%C3%BCr+Finanzen" in url


def test_fetch_parses_rss_fixture(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_presseportal.xml").read_text(encoding="utf-8")
    source = BerlinPresseportal()
    since = datetime(2026, 5, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = source.fetch(since)

    # Fixture has 4 items, all dated 2026-05-15 or later, plus one with no date
    # (parse_datetime fallback gives now() which is > since).
    assert len(items) == 4
    titles = [i.title for i in items]
    assert "Senatsverwaltung Jugend kuendigt Platzausbauprogramm Kita 2027 an" in titles
    assert all(i.source == "berlin_presseportal" for i in items)
    assert all(i.url.startswith("https://www.berlin.de/presse/") for i in items)
    assert all(i.snippet for i in items[:3])  # first 3 had descriptions


def test_fetch_filters_by_since_window(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_presseportal.xml").read_text(encoding="utf-8")
    source = BerlinPresseportal()
    # Anything older than ~5 minutes from now → none of the dated items pass,
    # but the undated one will (it falls back to now()).
    since = datetime.now(UTC) - timedelta(minutes=1)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = source.fetch(since)

    assert len(items) == 1
    assert items[0].title == "Item ohne Datum als Test"


def test_fetch_continues_on_http_failure(fixtures_dir: Path) -> None:
    """If HTTP fails, fetch should return [] without raising."""
    source = BerlinPresseportal()
    since = datetime(2026, 1, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", side_effect=RuntimeError("boom")):
        items = source.fetch(since)

    assert items == []


def test_item_id_is_stable_across_fetches(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_presseportal.xml").read_text(encoding="utf-8")
    source = BerlinPresseportal()
    since = datetime(2026, 5, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        a = source.fetch(since)
        b = source.fetch(since)

    assert {i.id for i in a} == {i.id for i in b}


def test_snippet_strips_html(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_presseportal.xml").read_text(encoding="utf-8")
    source = BerlinPresseportal()
    since = datetime(2026, 5, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = source.fetch(since)

    kita = next(i for i in items if "Platzausbauprogramm" in i.title)
    assert "<p>" not in kita.snippet
    assert "Antraege ab Juni" in kita.snippet
