"""Pydantic data models for the WNY news pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Topic(str, Enum):
    NEWS = "news"
    SPORTS = "sports"
    WEATHER = "weather"
    TRAFFIC = "traffic"
    CIVIC = "civic"
    EDUCATION = "education"
    OTHER = "other"


class RawStory(BaseModel):
    """Intermediate representation straight from a source adapter."""

    source: str
    adapter: str
    title: str
    url: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    section: Optional[str] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    fetch_metadata: dict = Field(default_factory=dict)


class NormalizedStory(BaseModel):
    """Fully normalised story ready for dedupe / ranking."""

    id: str
    source: str
    source_priority: float = 0.5
    region: str = "wny"
    topic: Topic = Topic.OTHER
    subtopic: Optional[str] = None
    title: str
    url: str
    canonical_url: str
    published_at: Optional[datetime] = None
    summary_input_text: str = ""
    snippet: Optional[str] = None
    content: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    is_official_source: bool = False
    dedupe_cluster_id: Optional[str] = None
    cross_source_count: int = 1
    score: float = 0.0
    debug_scores: dict = Field(default_factory=dict)


class StoryCluster(BaseModel):
    """A cluster of stories about the same event from multiple outlets."""

    cluster_id: str
    canonical_story: NormalizedStory
    all_sources: list[dict] = Field(default_factory=list)
    cross_source_count: int = 1


class GroupedSection(BaseModel):
    topic: str
    stories: list[NormalizedStory] = Field(default_factory=list)


class DigestOutput(BaseModel):
    generated_at: datetime
    time_window_hours: int
    top_stories: list[NormalizedStory] = Field(default_factory=list)
    summary: str = ""
    grouped_sections: list[GroupedSection] = Field(default_factory=list)
    run_report_ref: str = ""


class SourceReport(BaseModel):
    source: str
    status: str  # "ok" | "error" | "skipped"
    raw_count: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None


class RunReport(BaseModel):
    start_time: datetime
    end_time: datetime
    duration_seconds: float = 0.0
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    raw_count: int = 0
    normalized_count: int = 0
    deduped_count: int = 0
    final_count: int = 0
    errors: list[dict] = Field(default_factory=list)
    source_details: list[SourceReport] = Field(default_factory=list)
