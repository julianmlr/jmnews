"""Tests for the Brandenburg Vergabemarktplatz source (CPV 85 + CPV 80)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jmnews.sources.vergabe_brandenburg import (
    CPV_CATEGORIES,
    VergabeBrandenburg,
    build_category_url,
)

OLD = datetime(2020, 1, 1, tzinfo=UTC)


def _src() -> VergabeBrandenburg:
    src = VergabeBrandenburg()
    src.request_delay = 0  # no sleeping in tests
    return src


def test_polls_both_cpv_categories() -> None:
    assert [cpv for cpv, _ in CPV_CATEGORIES] == ["85000000-9", "80000000-4"]
    assert "cpvCode=80000000-4" in build_category_url("80000000-4")


def test_fetches_one_request_per_category(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    src = _src()
    with patch.object(VergabeBrandenburg, "_fetch_iso", return_value=raw) as mock:
        src.fetch(OLD)
    assert mock.call_count == len(CPV_CATEGORIES)
    called = [c.args[0] for c in mock.call_args_list]
    assert any("85000000-9" in u for u in called)
    assert any("80000000-4" in u for u in called)


def test_cpv_label_lands_in_snippet(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    src = _src()
    # Only the CPV 80 category returns rows, so items carry the Bildung label.
    with patch.object(
        VergabeBrandenburg, "_fetch_iso", side_effect=["<html></html>", raw]
    ):
        items = src.fetch(OLD)
    assert items
    assert all("CPV 80 Bildung" in i.snippet for i in items)


def test_dedupes_tender_listed_in_both_categories(fixtures_dir: Path) -> None:
    """Same tender under both CPV codes is kept once — CPV 85 wins."""
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    src = _src()
    with patch.object(VergabeBrandenburg, "_fetch_iso", return_value=raw):
        items = src.fetch(OLD)

    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)) == 2
    assert all("CPV 85 Sozialwesen" in i.snippet for i in items)


def test_parses_row_fields(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    src = _src()
    with patch.object(VergabeBrandenburg, "_fetch_iso", return_value=raw):
        items = src.fetch(OLD)

    unterkunft = next(i for i in items if "Gemeinschaftsunterkunft" in i.title)
    assert unterkunft.published_at.date().isoformat() == "2026-07-15"
    assert "Frist: 07.09.2026" in unterkunft.snippet
    assert "Landkreis Elbe-Elster" in unterkunft.snippet
    assert unterkunft.url.startswith("https://vergabemarktplatz.brandenburg.de/")
    # "nv" deadlines are not rendered as a Frist.
    grundbildung = next(i for i in items if "Grundbildungskurse" in i.title)
    assert "Frist:" not in grundbildung.snippet


def test_one_failing_category_does_not_kill_the_other(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    src = _src()
    with patch.object(
        VergabeBrandenburg, "_fetch_iso", side_effect=[RuntimeError("503"), raw]
    ):
        items = src.fetch(OLD)
    assert len(items) == 2  # CPV 80 still delivered


def test_returns_empty_when_all_categories_fail() -> None:
    src = _src()
    with patch.object(VergabeBrandenburg, "_fetch_iso", side_effect=RuntimeError("503")):
        assert src.fetch(OLD) == []


def test_filters_by_since(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    src = _src()
    with patch.object(VergabeBrandenburg, "_fetch_iso", return_value=raw):
        items = src.fetch(datetime(2026, 8, 1, tzinfo=UTC))
    titles = [i.title for i in items]
    assert any("Grundbildungskurse" in t for t in titles)  # 03.09.
    assert not any("Gemeinschaftsunterkunft" in t for t in titles)  # 15.07.
