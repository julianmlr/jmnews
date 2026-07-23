"""Tests for the Bodensee-region sources (KVJS Landesjugendamt, Südkurier)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jmnews.sources import enabled_sources
from jmnews.sources.base import parse_datetime
from jmnews.sources.kvjs import KVJS
from jmnews.sources.suedkurier import Suedkurier

OLD = datetime(2020, 1, 1, tzinfo=UTC)


# --- KVJS -------------------------------------------------------------------


def test_kvjs_parses_news_items(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "kvjs.html").read_text(encoding="utf-8")
    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = KVJS().fetch(OLD)

    assert len(items) == 2
    betrieb = next(i for i in items if "Betriebserlaubnis" in i.title)
    assert betrieb.url == (
        "https://www.kvjs.de/service/news/detailansicht/2026/06/"
        "betriebserlaubnis-heimaufsicht"
    )
    assert all(i.source == "kvjs" for i in items)


def test_kvjs_iso_date_not_dayfirst_flipped(fixtures_dir: Path) -> None:
    # datetime="2026-07-06" must stay 6 July, not flip to 7 June.
    raw = (fixtures_dir / "kvjs.html").read_text(encoding="utf-8")
    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = KVJS().fetch(OLD)

    aktuell = next(i for i in items if "KVJS Aktuell" in i.title)
    assert aktuell.published_at.date().isoformat() == "2026-07-06"


def test_kvjs_filters_by_since(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "kvjs.html").read_text(encoding="utf-8")
    since = datetime(2026, 7, 1, tzinfo=UTC)
    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = KVJS().fetch(since)

    # Only the 6 July item is in window; the 11 June one drops out.
    assert len(items) == 1
    assert "KVJS Aktuell" in items[0].title


# --- Südkurier --------------------------------------------------------------


def test_suedkurier_keeps_social_drops_noise(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "suedkurier.html").read_text(encoding="utf-8")
    with patch("jmnews.sources.suedkurier.http_get", return_value=raw):
        items = Suedkurier().fetch(OLD)

    titles = [i.title for i in items]
    assert any("Kita-Gebühren" in t for t in titles)
    assert any("Wohngruppe" in t for t in titles)
    # Local noise (Stadtfest, Autobrand) is filtered out.
    assert not any("Festmeile" in t for t in titles)
    assert not any("Flammen" in t for t in titles)
    assert all(i.source == "suedkurier" for i in items)


def test_suedkurier_title_from_aria_label_and_clean_url(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "suedkurier.html").read_text(encoding="utf-8")
    with patch("jmnews.sources.suedkurier.http_get", return_value=raw):
        items = Suedkurier().fetch(OLD)

    kita = next(i for i in items if "Kita-Gebühren" in i.title)
    # aria-label carries the clean headline; query string stripped from URL.
    assert kita.title.startswith("Ab September")
    assert kita.url.endswith("kita-gebuehren-steigen-das-sind-die-kosten-114763936")
    assert "?" not in kita.url


def test_suedkurier_returns_empty_on_http_failure() -> None:
    with patch("jmnews.sources.suedkurier.http_get", side_effect=RuntimeError("503")):
        assert Suedkurier().fetch(OLD) == []


# --- shared parse_datetime ISO fix ------------------------------------------


def test_parse_datetime_iso_vs_german() -> None:
    assert parse_datetime("2026-07-06 08:40").date().isoformat() == "2026-07-06"
    assert parse_datetime("2026-05-16").date().isoformat() == "2026-05-16"
    # German day-first is untouched.
    assert parse_datetime("12.05.2026").date().isoformat() == "2026-05-12"


# --- registration -----------------------------------------------------------


def test_bodensee_sources_registered() -> None:
    names = {s.name for s in enabled_sources()}
    assert "kvjs" in names
    assert "suedkurier" in names
