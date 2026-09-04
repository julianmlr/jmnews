"""Tests for the Berlin Vergabeplattform feed and the Gewaltschutz topic feed."""

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
from jmnews.sources.vergabe_berlin import FEED_URL, VergabeBerlin

OLD = datetime(2020, 1, 1, tzinfo=UTC)


# --- vergabe_berlin ---------------------------------------------------------


def _fetch(raw: str, since: datetime = OLD) -> list:
    with patch("jmnews.sources.base.http_get", return_value=raw):
        return VergabeBerlin().fetch(since)


def test_uses_single_feed_request_not_pagination() -> None:
    """One request instead of six paginated pages — that is the 429 fix."""
    src = VergabeBerlin()
    assert src.feed_urls() == [FEED_URL]
    assert FEED_URL.endswith("feed.rss")


def test_keeps_social_drops_construction(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.rss").read_text(encoding="utf-8")
    items = _fetch(raw)

    titles = [i.title for i in items]
    assert any("Flüchtlingsunterkünfte" in t for t in titles)
    assert any("Trägeraufruf Kita-Neubau" in t for t in titles)
    assert not any("Brunnenbau" in t for t in titles)
    assert not any("Dachdecker" in t for t in titles)
    assert all(i.source == "vergabe_berlin" for i in items)


def test_keeps_rib_detail_url_so_ids_stay_stable(fixtures_dir: Path) -> None:
    """The RIB URL is unchanged from the old HTML scraper, so already
    delivered tenders keep their id and are not re-alerted."""
    raw = (fixtures_dir / "vergabe_berlin.rss").read_text(encoding="utf-8")
    item = next(i for i in _fetch(raw) if "Flüchtlingsunterkünfte" in i.title)
    assert item.url == (
        "https://meinauftrag.rib.de/public/DetailsByPlatformIdAndTenderId/"
        "platformId/2/tenderId/301001"
    )


def test_snippet_carries_verfahrensart(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.rss").read_text(encoding="utf-8")
    items = _fetch(raw)
    kita = next(i for i in items if "Kita-Neubau" in i.title)
    # Below-threshold procedures (UVgO) are in the feed — TED never shows them.
    assert "UVgO" in kita.snippet
    assert "Ausführungsort" in kita.snippet


def test_filters_by_since(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_berlin.rss").read_text(encoding="utf-8")
    # pubDate carries +0200, so "02 Sep 00:00" is 01 Sep 22:00 UTC.
    items = _fetch(raw, since=datetime(2026, 9, 1, tzinfo=UTC))
    assert [i.title for i in items] == ["Betriebsleistungen für Flüchtlingsunterkünfte"]


def test_returns_empty_on_http_failure() -> None:
    with patch("jmnews.sources.base.http_get", side_effect=RuntimeError("503")):
        assert VergabeBerlin().fetch(OLD) == []


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
