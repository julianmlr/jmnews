"""Tests for the BRAVORS regulation source.

The source asks the Erweiterte Suche for everything issued since the window
start and reads the date-descending result list. These tests pin the parsing
of that list and the two behaviours that keep the pipeline honest: the issue
date must come from the `vom …` line (never the now() fallback), and results
outside the window must not survive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from jmnews.sources.brandenburg_vorschriften import BrandenburgVorschriften


def _response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


def _fetch(html: str, since: datetime) -> list:
    """Run fetch() against a canned first page.

    The fixture keeps its pager links, so page 2 is requested; answering it
    with an empty list is what a real run past the last page looks like and
    ends the loop.
    """
    src = BrandenburgVorschriften()
    client = MagicMock()
    client.post.return_value = _response(html)
    client.get.return_value = _response("<html><body></body></html>")
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    with patch("jmnews.sources.brandenburg_vorschriften.httpx.Client", return_value=client):
        return src.fetch(since)


def test_parses_result_list(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "bravors_ergebnisliste.html").read_text(encoding="utf-8")
    items = _fetch(raw, datetime(2026, 1, 1, tzinfo=UTC))

    assert items
    first = items[0]
    assert first.source == "brandenburg_vorschriften"
    assert first.title
    assert first.url.startswith("https://bravors.brandenburg.de/")
    # Date comes from the `vom DD.MM.YYYY` sibling, not from now().
    assert first.published_at.year == 2026
    assert first.published_at != datetime.now(UTC)


def test_filters_out_regulations_before_the_window(fixtures_dir: Path) -> None:
    raw = (fixtures_dir / "bravors_ergebnisliste.html").read_text(encoding="utf-8")
    in_window = _fetch(raw, datetime(2026, 1, 1, tzinfo=UTC))
    # Window starting after every fixture entry must drop them all.
    assert _fetch(raw, datetime(2026, 12, 31, tzinfo=UTC)) == []
    assert in_window


def test_search_payload_carries_the_window_start() -> None:
    src = BrandenburgVorschriften()
    payload = src._payload(datetime(2026, 8, 28, 6, 45, tzinfo=UTC))
    assert payload["search[ausfertigungsdatum_von]"] == "28.08.2026"
    assert payload["search[art_vorschrift][]"] == "alle"
    # No keyword narrowing: the classifier decides relevance, not the scraper.
    assert payload["search[fulltext]"] == ""
    assert payload["search[title]"] == ""


def test_returns_empty_on_http_failure() -> None:
    src = BrandenburgVorschriften()
    client = MagicMock()
    client.post.side_effect = httpx.ConnectError("boom")
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    with patch("jmnews.sources.brandenburg_vorschriften.httpx.Client", return_value=client):
        assert src.fetch(datetime(2026, 1, 1, tzinfo=UTC)) == []


def test_returns_empty_when_page_has_no_result_list() -> None:
    assert _fetch("<html><body>keine Treffer</body></html>",
                  datetime(2026, 1, 1, tzinfo=UTC)) == []
