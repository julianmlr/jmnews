"""Tests for jmnews.models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jmnews.models import FilterResult, NewsItem, stable_id


def test_stable_id_is_deterministic() -> None:
    url = "https://example.com/article/123"
    assert stable_id(url) == stable_id(url)
    assert stable_id(url) != stable_id(url + "?x=1")


def test_stable_id_trims_whitespace() -> None:
    assert stable_id("https://example.com/x") == stable_id("  https://example.com/x  ")


def test_snippet_truncated_to_500_chars() -> None:
    item = NewsItem(
        id="abc",
        source="test",
        title="t",
        url="https://e.com/x",
        published_at=datetime(2026, 5, 16, tzinfo=UTC),
        snippet="x" * 1000,
    )
    assert len(item.snippet) == 500
    assert item.snippet.endswith("...")


def test_filter_result_score_bounds() -> None:
    with pytest.raises(ValidationError):
        FilterResult(id="a", score=11, category="action")
    with pytest.raises(ValidationError):
        FilterResult(id="a", score=-1, category="ignore")
    fr = FilterResult(id="a", score=7, category="relevant", reasoning="kurz")
    assert fr.category == "relevant"


def test_filter_result_category_validated() -> None:
    with pytest.raises(ValidationError):
        FilterResult(id="a", score=5, category="maybe")  # type: ignore[arg-type]
