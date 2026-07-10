"""Tests for the Trägeraufruf sources (searchtext feeds + berlin.de scrapers)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jmnews.sources.berlin_jugendaemter import (
    JUGENDAMT_PAGES,
    JugendamtAktuelles,
    SenBJFAusschreibungen,
    jugendamt_sources,
)
from jmnews.sources.berlin_traegeraufrufe import (
    SEARCH_TERMS,
    BerlinTraegeraufrufe,
    build_search_feed_url,
)

OLD = datetime(2020, 1, 1, tzinfo=UTC)


def test_search_feed_url_encodes_term() -> None:
    url = build_search_feed_url("Trägeraufruf")
    assert url.endswith("?searchtext=Tr%C3%A4geraufruf")


def test_feed_urls_one_per_term() -> None:
    src = BerlinTraegeraufrufe()
    urls = src.feed_urls()
    assert len(urls) == len(SEARCH_TERMS)
    assert all("searchtext=" in u for u in urls)


def test_request_delay_configured_against_429() -> None:
    # berlin.de answers rapid feed hits with "429 Calm down".
    assert BerlinTraegeraufrufe.request_delay > 0


def test_fetch_dedupes_across_keyword_feeds(fixtures_dir: Path) -> None:
    # The same PM matches several search terms; the item must appear once.
    raw = (fixtures_dir / "berlin_presseportal.xml").read_text(encoding="utf-8")
    src = BerlinTraegeraufrufe()
    src.request_delay = 0  # no sleeping in tests

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(OLD)

    urls = [i.url for i in items]
    assert len(urls) == len(set(urls))
    assert items
    assert all(i.source == "berlin_traegeraufrufe" for i in items)


def test_jugendamt_sources_have_unique_names() -> None:
    sources = jugendamt_sources()
    assert len(sources) == len(JUGENDAMT_PAGES)
    names = [s.name for s in sources]
    assert len(names) == len(set(names))
    assert all(s.page_url.startswith("https://www.berlin.de/ba-") for s in sources)


def test_jugendamt_parses_list_module(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_jugendamt_liste.html").read_text(encoding="utf-8")
    src = JugendamtAktuelles(
        "treptow_koepenick", JUGENDAMT_PAGES["treptow_koepenick"]
    )

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(OLD)

    assert len(items) == 2
    aufruf = next(i for i in items if "Angebotsabgabe" in i.title)
    assert aufruf.url == (
        "https://www.berlin.de/ba-treptow-koepenick/politik-und-verwaltung/"
        "aemter/jugendamt/aktuelles/artikel.1603469.php"
    )
    assert "freie Träger" in aufruf.snippet
    assert aufruf.source == "jugendamt_treptow_koepenick"


def test_senbjf_parses_download_module(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "senbjf_ausschreibungen.html").read_text(encoding="utf-8")
    src = SenBJFAusschreibungen()

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(OLD)

    assert len(items) == 1
    item = items[0]
    assert item.title == "Ausschreibung Yad Vashem Gedenkstättenfahrt 2026"
    assert item.url.startswith(
        "https://www.berlin.de/sen/bjf/service/ausschreibungen/"
    )
    assert "Fortbildungsangebot" in item.snippet
