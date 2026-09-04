"""Tests for the public software-tender sources (TED + Länder portals).

Both express the same intent — surface tenders a small vendor can bid on
without clearing a reference gate first — through the procedure type: TED's
``open`` and the portals' absence of a Teilnahmewettbewerb.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from jmnews.sources import enabled_sources
from jmnews.sources.vergabe_software_laender import (
    CPV_CODES,
    PORTALS,
    VergabeSoftwareLaender,
)
from jmnews.sources.vergabe_software_ted import VergabeSoftwareTED, build_query

OLD = datetime(2020, 1, 1, tzinfo=UTC)


# --- TED --------------------------------------------------------------------


def test_query_excludes_reference_gated_and_awarded() -> None:
    q = build_query()
    # Only live opportunities...
    assert "notice-type IN (cn-standard)" in q
    # ...in the single-stage procedure, so no Teilnahmewettbewerb.
    assert "procedure-type IN (open)" in q
    assert "neg-w-call" not in q
    assert "restricted" not in q
    assert "buyer-country IN (DEU)" in q
    assert "72000000" in q and "48000000" in q


def _ted_response(notices: list[dict]) -> object:
    class R:
        status_code = 200

        def raise_for_status(self) -> None: ...

        def json(self) -> dict:
            return {"notices": notices}

    return R()


def test_maps_notice_to_item() -> None:
    notice = {
        "publication-number": "581702-2026",
        "title-proc": {"deu": "Ausbauphase des Familienportals"},
        "buyer-name": {"deu": ["Ministerium für Arbeit und Soziales"]},
        "publication-date": "2026-08-24+02:00",
        "deadline-date-lot": ["2026-09-30+02:00"],
        "estimated-value-lot": ["250000"],
    }
    with patch("httpx.Client.post", return_value=_ted_response([notice])):
        items = VergabeSoftwareTED().fetch(OLD)

    assert len(items) == 1
    item = items[0]
    assert item.title == "Ausbauphase des Familienportals"
    assert item.url == "https://ted.europa.eu/de/notice/581702-2026"
    assert item.published_at.date().isoformat() == "2026-08-24"
    assert "keine Referenz-Vorrunde" in item.snippet
    assert "Frist: 2026-09-30" in item.snippet
    assert "250.000 EUR" in item.snippet
    assert item.source == "vergabe_software_ted"


def test_skips_notices_without_number_or_title() -> None:
    with patch("httpx.Client.post", return_value=_ted_response([{"title-proc": {}}])):
        assert VergabeSoftwareTED().fetch(OLD) == []


def test_ted_returns_empty_on_api_failure() -> None:
    with patch("httpx.Client.post", side_effect=RuntimeError("502")):
        assert VergabeSoftwareTED().fetch(OLD) == []


# --- Länder portals ---------------------------------------------------------


def _laender(raw: str) -> list:
    src = VergabeSoftwareLaender()
    src.request_delay = 0
    with patch.object(VergabeSoftwareLaender, "_fetch_iso", return_value=raw):
        return src.fetch(OLD)


def test_targets_cover_every_portal_and_cpv() -> None:
    targets = VergabeSoftwareLaender().targets()
    assert len(targets) == len(PORTALS) * len(CPV_CODES)
    for land, host in PORTALS:
        assert any(host in url and label == land for url, label in targets)
    # Both software CPV families are queried.
    assert any("72000000" in u for u, _ in targets)
    assert any("48000000" in u for u, _ in targets)


def test_land_label_lands_in_snippet(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    items = _laender(raw)

    # Each portal contributes its own rows (different hosts → different URLs),
    # but the two CPV queries per portal are deduped: 3 portals x 2 rows, not x4.
    assert len(items) == len(PORTALS) * 2
    assert len({i.id for i in items}) == len(items)
    for land, _ in PORTALS:
        assert any(i.snippet.endswith(land) for i in items)
    assert all(i.source == "vergabe_software_laender" for i in items)


@pytest.mark.parametrize(
    "verfahrensart",
    ["UVgO TNW", "VgV Verhandlungsverfahren mit Teilnahmewettbewerb", "Nicht offenes Verfahren"],
)
def test_drops_reference_gated_procedures(fixtures_dir: Path, verfahrensart: str) -> None:
    raw = (fixtures_dir / "vergabe_brandenburg.html").read_text(encoding="utf-8")
    gated = raw.replace("UVgO Beabsichtigte Ausschreibung", verfahrensart)
    titles = [i.title for i in _laender(gated)]
    assert "Grundbildungskurse im Landkreis OPR" not in titles
    # The untouched row survives, so the filter is targeted, not a blanket drop.
    assert "Betreibung einer Gemeinschaftsunterkunft" in titles


def test_registered() -> None:
    names = {s.name for s in enabled_sources()}
    assert "vergabe_software_ted" in names
    assert "vergabe_software_laender" in names
