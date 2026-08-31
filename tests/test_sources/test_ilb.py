"""Tests for the ILB programme-news source.

ILB renders client-side, so the source reads the `__NUXT_DATA__` payload
instead of the DOM. Nuxt flattens everything into one array in which every
value — object keys included — is an index into that same array, so the
resolver is the part worth pinning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from jmnews.sources.ilb import ILB

PAGES = (("Infrastruktur", "https://www.ilb.de/de/infrastruktur/alle-infrastruktur-foerderprogramme/"),)


def _fetch(html: str, since: datetime, pages=PAGES) -> list:
    src = ILB(pages=pages)
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = response
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    with patch("jmnews.sources.ilb.httpx.Client", return_value=client):
        return src.fetch(since)


@pytest.fixture
def payload_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "ilb_nuxt_payload.html").read_text(encoding="utf-8")


def test_extracts_news_entry_from_nuxt_payload(payload_html: str) -> None:
    items = _fetch(payload_html, datetime(2026, 1, 1, tzinfo=UTC))

    assert len(items) == 1
    item = items[0]
    assert item.source == "ilb"
    assert item.title == "1. Richtlinienänderung"
    assert item.published_at.date().isoformat() == "2026-07-09"
    # Rich-text kurztext is flattened into the snippet, behind the area label.
    assert item.snippet.startswith("ILB-Förderung Infrastruktur | ")
    assert "Energetische Sanierung" in item.snippet
    assert item.url == PAGES[0][1]


def test_filters_by_window(payload_html: str) -> None:
    assert _fetch(payload_html, datetime(2026, 8, 1, tzinfo=UTC)) == []


def test_same_entry_on_two_pages_is_deduplicated(payload_html: str) -> None:
    pages = (
        ("Infrastruktur", "https://www.ilb.de/de/a/"),
        ("Infrastruktur", "https://www.ilb.de/de/a/"),
    )
    assert len(_fetch(payload_html, datetime(2026, 1, 1, tzinfo=UTC), pages=pages)) == 1


def test_returns_empty_when_payload_is_missing() -> None:
    assert _fetch("<html><body>no payload</body></html>",
                  datetime(2026, 1, 1, tzinfo=UTC)) == []


def test_returns_empty_on_http_failure() -> None:
    src = ILB(pages=PAGES)
    client = MagicMock()
    client.get.side_effect = httpx.ConnectError("boom")
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    with patch("jmnews.sources.ilb.httpx.Client", return_value=client):
        assert src.fetch(datetime(2026, 1, 1, tzinfo=UTC)) == []
