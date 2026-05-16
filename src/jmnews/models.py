"""Pydantic models for items, filter results, briefings, runs."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["ignore", "context", "relevant", "action"]


def stable_id(url: str) -> str:
    """Stable 16-char hex id derived from the canonical URL."""
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


class NewsItem(BaseModel):
    """A normalised news item collected from a source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    source: str
    title: str
    url: str
    published_at: datetime
    snippet: str = ""
    raw_html: str | None = None

    # filter results (populated after filter stage)
    score: int | None = None
    category: Category | None = None
    reasoning: str | None = None

    # bookkeeping
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    delivered_in_briefing_id: str | None = None

    @field_validator("snippet")
    @classmethod
    def _truncate_snippet(cls, v: str) -> str:
        if v and len(v) > 500:
            return v[:497] + "..."
        return v


class FilterResult(BaseModel):
    """LLM-produced classification for a single item."""

    id: str
    score: int = Field(ge=0, le=10)
    category: Category
    reasoning: str = ""

    @field_validator("reasoning")
    @classmethod
    def _truncate_reasoning(cls, v: str) -> str:
        if v and len(v) > 500:
            return v[:497] + "..."
        return v


class Briefing(BaseModel):
    """A generated daily briefing."""

    id: str  # YYYY-MM-DD
    generated_at: datetime
    markdown: str
    item_count: int
    delivered_at: datetime | None = None
    delivery_status: Literal["pending", "telegram", "file", "failed"] = "pending"


class Run(BaseModel):
    """A single pipeline run for audit purposes."""

    id: str
    kind: Literal["collect", "filter", "deliver", "full"]
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "success", "failed"] = "running"
    error: str | None = None
