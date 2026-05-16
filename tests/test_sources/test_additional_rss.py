"""Parametrized tests for the Stage 8 RSS sources.

These all extend RSSSource (covered in detail by test_berlin_presseportal),
so per source we only verify: the default URL is present, the parser
produces normalized items with the source's name, and items can be
filtered by `since`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from jmnews.sources import enabled_sources
from jmnews.sources.berliner_zeitung import BerlinerZeitung
from jmnews.sources.nbf import NbF
from jmnews.sources.rbb24 import Rbb24
from jmnews.sources.taz_berlin import TazBerlin

SOURCE_CLASSES = [BerlinerZeitung, TazBerlin, Rbb24, NbF]


@pytest.mark.parametrize("source_cls", SOURCE_CLASSES)
def test_each_source_has_default_url(source_cls) -> None:
    assert source_cls.DEFAULT_URL.startswith("http")
    assert source_cls().feed_urls() == [source_cls.DEFAULT_URL]


@pytest.mark.parametrize("source_cls", SOURCE_CLASSES)
def test_each_source_parses_generic_rss(
    source_cls, fixtures_dir: Path
) -> None:
    raw = (fixtures_dir / "generic_rss.xml").read_text(encoding="utf-8")
    source = source_cls()
    since = datetime(2026, 5, 1, tzinfo=UTC)

    with patch("jmnews.sources.base.http_get", return_value=raw):
        items = source.fetch(since)

    assert len(items) == 2
    assert all(item.source == source_cls.name for item in items)
    assert all(item.url.startswith("https://example.com/") for item in items)


def test_enabled_sources_includes_all_five_stage8_sources() -> None:
    names = {s.name for s in enabled_sources()}
    expected = {
        "berlin_presseportal",
        "tagesspiegel",
        "berliner_zeitung",
        "taz_berlin",
        "rbb24",
    }
    assert expected <= names
