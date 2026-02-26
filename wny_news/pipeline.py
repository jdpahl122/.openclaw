"""End-to-end pipeline: fetch → normalise → dedupe → rank → summarise → output.

Designed to be cron-friendly: returns 0 on partial success, non-zero only if
the *entire* pipeline fails.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from config import (
    DEFAULT_HOURS,
    DEFAULT_TOP_N,
    OFFICIAL_SOURCES,
    OUTPUT_DIR,
    SOURCE_PRIORITIES,
    SPORTS_TEAMS,
)
from dedupe import deduplicate
from models import (
    DigestOutput,
    NormalizedStory,
    RawStory,
    RunReport,
    SourceReport,
    StoryCluster,
    Topic,
)
from ranking import rank_clusters
from sources import ALL_ADAPTERS
from summarizer import (
    build_digest_markdown,
    build_digest_summary,
    compact_payload,
)
from utils.text import clean_text, first_sentences, normalise_url, story_id
from utils.time import is_within_window, now_utc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_wny_digest(
    *,
    hours: int = DEFAULT_HOURS,
    top_n: int = DEFAULT_TOP_N,
    topic: str | None = None,
    output_dir: str | None = None,
) -> dict:
    """Run the full pipeline and return a result dict.

    This is the main entry point for both the CLI and programmatic callers
    (e.g., OpenClaw skill wrappers).
    """
    out = Path(output_dir or OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    report = _RunState()
    report.start()

    # 1) Fetch from all sources
    raw_stories = _fetch_all(report)

    # 2) Normalise
    normalised = _normalise(raw_stories, hours=hours)
    report.normalized_count = len(normalised)

    # 3) Dedupe / cluster
    clusters = deduplicate(normalised)
    report.deduped_count = len(clusters)

    # 4) Rank
    ranked = rank_clusters(clusters, hours=hours, topic_filter=topic)

    # 5) Take top N
    top = ranked[:top_n]
    report.final_count = len(top)

    # 6) Summarise
    digest_md = build_digest_markdown(top, hours=hours)
    digest_summary = build_digest_summary(top)

    # 7) Write outputs
    report.finish()
    run_report = report.to_model()

    _write_json(out / "top_stories.json", [s.model_dump(mode="json") for s in top])
    _write_text(out / "digest.md", digest_md)
    _write_json(out / "run_report.json", run_report.model_dump(mode="json"))

    logger.info(
        "Pipeline complete: %d raw → %d normalised → %d clusters → %d final (%.1fs)",
        report.raw_count, report.normalized_count, report.deduped_count,
        report.final_count, run_report.duration_seconds,
    )

    return {
        "status": "ok",
        "stories": compact_payload(top),
        "summary": digest_summary,
        "story_count": len(top),
        "digest_path": str(out / "digest.md"),
        "report_path": str(out / "run_report.json"),
        "run_report": run_report.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _fetch_all(report: _RunState) -> list[RawStory]:
    all_raw: list[RawStory] = []
    for adapter_cls in ALL_ADAPTERS:
        adapter = adapter_cls()
        report.sources_attempted += 1
        t0 = time.monotonic()
        try:
            items = adapter.fetch()
            elapsed = (time.monotonic() - t0) * 1000
            all_raw.extend(items)
            report.add_source(adapter.name, "ok", len(items), elapsed)
            report.sources_succeeded += 1
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("Source %s failed: %s", adapter.name, exc)
            report.add_source(adapter.name, "error", 0, elapsed, str(exc))
            report.sources_failed += 1

    report.raw_count = len(all_raw)
    return all_raw


# ---------------------------------------------------------------------------
# Normalise
# ---------------------------------------------------------------------------

_CIVIC_KEYWORDS = [
    "city hall", "common council", "mayor", "ordinance", "public hearing",
    "road closure", "water main", "snow emergency", "parking ban",
]

_WEATHER_KEYWORDS = [
    "weather", "forecast", "snow", "lake effect", "blizzard", "tornado",
    "severe storm", "heat advisory", "wind chill",
]

_TRAFFIC_KEYWORDS = [
    "traffic", "accident", "closure", "detour", "i-90", "i-190", "thruway",
    "kensington", "scajaquada",
]


def _classify_topic(story: RawStory) -> tuple[Topic, str | None]:
    """Keyword-based topic classifier.  Returns (topic, subtopic)."""
    text = f"{story.title} {story.snippet or ''} {' '.join(story.tags)}".lower()

    # Sports teams check
    for team_info in SPORTS_TEAMS.values():
        for kw in team_info["keywords"]:
            if kw in text:
                return Topic.SPORTS, team_info["subtopic"]

    if story.section and "sport" in story.section.lower():
        return Topic.SPORTS, None
    if any(kw in text for kw in _WEATHER_KEYWORDS):
        return Topic.WEATHER, None
    if any(kw in text for kw in _TRAFFIC_KEYWORDS):
        return Topic.TRAFFIC, None
    if any(kw in text for kw in _CIVIC_KEYWORDS):
        return Topic.CIVIC, None
    if story.source == "city_of_buffalo":
        return Topic.CIVIC, "city_hall"
    if story.source == "ub":
        return Topic.EDUCATION, "ub"
    return Topic.NEWS, None


def _normalise(raw: list[RawStory], *, hours: int) -> list[NormalizedStory]:
    results: list[NormalizedStory] = []
    for r in raw:
        if not is_within_window(r.published_at, hours):
            continue

        topic, subtopic = _classify_topic(r)
        canonical = normalise_url(r.url)
        sid = story_id(r.source, r.url)

        summary_input = r.snippet or ""
        if r.content:
            summary_input = first_sentences(r.content, 3)

        results.append(NormalizedStory(
            id=sid,
            source=r.source,
            source_priority=SOURCE_PRIORITIES.get(r.source, 0.5),
            topic=topic,
            subtopic=subtopic,
            title=r.title,
            url=r.url,
            canonical_url=canonical,
            published_at=r.published_at,
            summary_input_text=summary_input,
            snippet=r.snippet,
            content=r.content,
            entities=[],
            is_official_source=r.source in OFFICIAL_SOURCES,
        ))

    logger.info("Normalised %d items (from %d raw, %dh window)", len(results), len(raw), hours)
    return results


# ---------------------------------------------------------------------------
# Run state tracker
# ---------------------------------------------------------------------------

class _RunState:
    def __init__(self) -> None:
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.sources_attempted = 0
        self.sources_succeeded = 0
        self.sources_failed = 0
        self.raw_count = 0
        self.normalized_count = 0
        self.deduped_count = 0
        self.final_count = 0
        self._source_details: list[SourceReport] = []
        self._errors: list[dict] = []

    def start(self) -> None:
        self.start_time = now_utc()

    def finish(self) -> None:
        self.end_time = now_utc()

    def add_source(
        self, name: str, status: str, count: int, elapsed_ms: float,
        error: str | None = None,
    ) -> None:
        self._source_details.append(SourceReport(
            source=name, status=status, raw_count=count,
            duration_ms=elapsed_ms, error=error,
        ))
        if error:
            self._errors.append({"source": name, "error": error})

    def to_model(self) -> RunReport:
        start = self.start_time or now_utc()
        end = self.end_time or now_utc()
        return RunReport(
            start_time=start,
            end_time=end,
            duration_seconds=round((end - start).total_seconds(), 2),
            sources_attempted=self.sources_attempted,
            sources_succeeded=self.sources_succeeded,
            sources_failed=self.sources_failed,
            raw_count=self.raw_count,
            normalized_count=self.normalized_count,
            deduped_count=self.deduped_count,
            final_count=self.final_count,
            errors=self._errors,
            source_details=self._source_details,
        )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    logger.debug("Wrote %s", path)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text + "\n")
    logger.debug("Wrote %s", path)
