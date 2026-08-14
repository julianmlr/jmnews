"""Tests for the SenBJF Aufsicht source (Heimaufsicht §45 SGB VIII + Kitaaufsicht)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jmnews.sources import enabled_sources
from jmnews.sources.berlin_aufsicht import AUFSICHT_PAGES, BerlinAufsicht

OLD = datetime(2020, 1, 1, tzinfo=UTC)
ONE_PAGE = (("Heimaufsicht (Einrichtungsaufsicht §45 SGB VIII)", "https://x/test"),)


def _fetch(raw: str, pages=ONE_PAGE) -> list:
    src = BerlinAufsicht(pages)
    src.request_delay = 0  # no sleeping in tests
    with patch("jmnews.sources.berlin_aufsicht.http_get", return_value=raw):
        return src.fetch(OLD)


def test_parses_download_modules(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_aufsicht.html").read_text(encoding="utf-8")
    items = _fetch(raw)

    assert len(items) == 3
    titles = [i.title for i in items]
    assert any("Betriebserlaubnis" in t for t in titles)
    assert all(i.source == "berlin_aufsicht" for i in items)


def test_strips_ts_cache_buster_from_url(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_aufsicht.html").read_text(encoding="utf-8")
    items = _fetch(raw)

    infoblatt = next(i for i in items if "Neugründung" in i.title)
    assert infoblatt.url == (
        "https://www.berlin.de/sen/jugend/familie-und-kinder/aufsicht/"
        "einrichtungsaufsicht-fachinfo/infoblatt-fuer-neutraeger.pdf"
    )
    assert "?ts=" not in infoblatt.url


def test_snippet_carries_label_and_stand(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_aufsicht.html").read_text(encoding="utf-8")
    items = _fetch(raw)

    infoblatt = next(i for i in items if "Neugründung" in i.title)
    assert "Heimaufsicht" in infoblatt.snippet
    assert "Stand: Juli 2024" in infoblatt.snippet
    # A module without a "Stand:" caption still yields a usable snippet.
    rundschreiben = next(i for i in items if "Trägerrundschreiben" in i.title)
    assert "Heimaufsicht" in rundschreiben.snippet
    assert "Stand:" not in rundschreiben.snippet


def test_id_changes_with_stand_not_with_ts(fixtures_dir: Path) -> None:
    """Version identity comes from the editorial "Stand", not the mtime buster."""
    raw = (fixtures_dir / "berlin_aufsicht.html").read_text(encoding="utf-8")
    baseline = {i.title: i.id for i in _fetch(raw)}

    # A CMS bulk migration bumps every ts but no content: IDs must hold.
    retouched = raw.replace("ts=1753089048", "ts=1799999999").replace(
        "ts=1756971908", "ts=1799999998"
    )
    assert {i.title: i.id for i in _fetch(retouched)} == baseline

    # A genuinely re-issued document bumps "Stand": that must alert anew.
    reissued = raw.replace("Stand: Juli 2024", "Stand: März 2026")
    new_ids = {i.title: i.id for i in _fetch(reissued)}
    assert new_ids["Infoblatt bei Neugründung"] != baseline["Infoblatt bei Neugründung"]
    # Untouched documents keep their identity.
    assert new_ids["Trägerrundschreiben Fachkräfteregelung"] == (
        baseline["Trägerrundschreiben Fachkräfteregelung"]
    )


def test_dedupes_across_pages(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "berlin_aufsicht.html").read_text(encoding="utf-8")
    # Both configured pages return the same HTML → each document once.
    items = _fetch(raw, pages=AUFSICHT_PAGES)
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)) == 3


def test_returns_empty_on_http_failure() -> None:
    src = BerlinAufsicht(ONE_PAGE)
    src.request_delay = 0
    with patch("jmnews.sources.berlin_aufsicht.http_get", side_effect=RuntimeError("503")):
        assert src.fetch(OLD) == []


def test_covers_both_heim_and_kita_aufsicht() -> None:
    labels = " ".join(label for label, _ in AUFSICHT_PAGES)
    urls = " ".join(url for _, url in AUFSICHT_PAGES)
    assert "Heimaufsicht" in labels
    assert "Kitaaufsicht" in labels
    assert "einrichtungsaufsicht-fachinfo" in urls
    assert "kitaaufsicht/fachinfo" in urls


def test_not_in_alarm_sources() -> None:
    # Aufsichts-Vorgaben are reference documents, not Trägeraufrufe.
    from jmnews.briefing import _TRAEGERAUFRUF_SOURCES

    assert "berlin_aufsicht" not in _TRAEGERAUFRUF_SOURCES


def test_registered() -> None:
    assert "berlin_aufsicht" in {s.name for s in enabled_sources()}
