"""Score and rank stories for the digest.

Each dimension produces a 0.0–1.0 sub-score.  The final score is a
weighted sum controlled by ``config.RANKING_WEIGHTS``.
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta

from config import (
    OFFICIAL_SOURCES,
    RANKING_WEIGHTS,
    SOURCE_PRIORITIES,
    SPORTS_TEAMS,
    TOPIC_PRIORITIES,
)
from models import NormalizedStory, StoryCluster
from utils.time import ensure_utc, now_utc

logger = logging.getLogger(__name__)

# Max age beyond which recency score drops to zero
_MAX_AGE_HOURS = 72


def rank_clusters(
    clusters: list[StoryCluster],
    *,
    hours: int = 24,
    topic_filter: str | None = None,
) -> list[NormalizedStory]:
    """Score every cluster's canonical story and return them sorted descending."""

    scored: list[NormalizedStory] = []
    for cluster in clusters:
        story = cluster.canonical_story
        story.cross_source_count = cluster.cross_source_count
        _score(story, hours=hours)
        scored.append(story)

    if topic_filter:
        scored = [s for s in scored if s.topic.value == topic_filter]

    scored.sort(key=lambda s: s.score, reverse=True)
    logger.info("Ranked %d stories (top score: %.3f)", len(scored), scored[0].score if scored else 0)
    return scored


def _score(story: NormalizedStory, *, hours: int) -> None:
    w = RANKING_WEIGHTS
    debug: dict[str, float] = {}

    debug["recency"] = _recency(story, hours)
    debug["source_priority"] = SOURCE_PRIORITIES.get(story.source, 0.5)
    debug["topic_priority"] = TOPIC_PRIORITIES.get(story.topic.value, 0.4)
    debug["sports_boost"] = _sports_boost(story)
    debug["cross_source_boost"] = _cross_source(story)
    debug["official_source_boost"] = 1.0 if story.is_official_source else 0.0

    total = sum(debug[k] * w.get(k, 0) for k in debug)
    story.score = round(min(total, 1.0), 4)
    story.debug_scores = {k: round(v, 4) for k, v in debug.items()}


def _recency(story: NormalizedStory, hours: int) -> float:
    if story.published_at is None:
        return 0.5  # unknown date gets a neutral score
    age = (now_utc() - ensure_utc(story.published_at)).total_seconds() / 3600
    if age <= 0:
        return 1.0
    if age >= _MAX_AGE_HOURS:
        return 0.0
    # Exponential decay so stories age off smoothly
    return math.exp(-2.0 * age / _MAX_AGE_HOURS)


def _sports_boost(story: NormalizedStory) -> float:
    text = f"{story.title} {story.snippet or ''} {story.subtopic or ''}".lower()
    best = 0.0
    for team_info in SPORTS_TEAMS.values():
        for kw in team_info["keywords"]:
            if kw in text:
                best = max(best, team_info["boost"])
    # Normalise the boost value to 0–1 range (max boost is 0.15)
    return min(best / 0.15, 1.0) if best else 0.0


def _cross_source(story: NormalizedStory) -> float:
    # 1 source = 0.0, 2 = 0.5, 3+ = 1.0
    c = story.cross_source_count
    if c <= 1:
        return 0.0
    if c == 2:
        return 0.5
    return 1.0
