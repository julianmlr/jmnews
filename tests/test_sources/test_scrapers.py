"""Tests for the Stage 9 HTML scraping sources.

All six share the same ScrapingSource base; we exercise the parser end-to-end
through one source and parametrize a smoke test across the rest.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from jmnews.sources import enabled_sources
from jmnews.sources.brandenburg_vorschriften import BrandenburgVorschriften
from jmnews.sources.bsfz import BSFZ
from jmnews.sources.daks import DaKS
from jmnews.sources.diakonie_bb import DiakonieBB
from jmnews.sources.ibb import IBB
from jmnews.sources.ilb import ILB
from jmnews.sources.paritaet_berlin import ParitaetBerlin

SCRAPER_CLASSES = [
    IBB, ILB, BSFZ, DaKS, BrandenburgVorschriften, ParitaetBerlin, DiakonieBB,
]


@pytest.mark.parametrize("source_cls", SCRAPER_CLASSES)
def test_each_scraper_has_required_config(source_cls) -> None:
    src = source_cls()
    assert src.page_url.startswith("http")
    assert src.name
    assert src.selectors.container


def test_ibb_parses_generic_fixture_via_selectolax(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "generic_scrape.html").read_text(encoding="utf-8")
    src = IBB()
    since = datetime(2026, 5, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(since)

    assert len(items) == 2
    titles = [i.title for i in items]
    assert "Neue Foerderlinie fuer Kita-Plaetze" in titles
    # relative URLs are resolved against base_url
    foerder = next(i for i in items if "Foerderlinie" in i.title)
    assert foerder.url == "https://www.ibb.de/news/2026/05/16/foerderlinie-kita"
    # absolute URLs in the page are preserved
    vorstand = next(i for i in items if "Vorstandswechsel" in i.title)
    assert vorstand.url == "https://example.com/news/2026/05/15/vorstand"
    # date pulled from `datetime` attribute
    assert foerder.published_at.date().isoformat() == "2026-05-16"


def test_scraper_filters_by_since(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "generic_scrape.html").read_text(encoding="utf-8")
    src = IBB()
    since = datetime(2026, 5, 16, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = src.fetch(since)

    # only the May 16 item is in window
    assert len(items) == 1
    assert "Foerderlinie" in items[0].title


def test_scraper_returns_empty_on_http_failure() -> None:
    src = IBB()
    since = datetime(2026, 1, 1, tzinfo=UTC)
    with patch("jmnews.sources.base.http_get", side_effect=RuntimeError("503")):
        assert src.fetch(since) == []


def test_scraper_returns_empty_on_unparsable_html() -> None:
    src = IBB()
    since = datetime(2026, 1, 1, tzinfo=UTC)
    with patch("jmnews.sources.base.http_get", return_value="<html><body>nothing</body></html>"):
        items = src.fetch(since)
    assert items == []


def test_enabled_sources_includes_all_configured() -> None:
    names = {s.name for s in enabled_sources()}
    expected = {
        # RSS / feeds / sitemap
        "berlin_presseportal",
        "tagesspiegel",
        "berliner_zeitung",
        "taz_berlin",
        "rbb24",
        "nbf",
        "dsee",
        # scrapers
        "ibb",
        "ilb",
        "bsfz",
        "daks",
        "paritaet_berlin",
        "diakonie_bb",
        "brandenburg_vorschriften",
    }
    assert expected <= names
