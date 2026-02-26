"""Deduplicate / cluster stories that cover the same event across outlets.

Strategy (deliberately simple, not overengineered):
1. Normalise canonical URLs → exact match = same story.
2. Fuzzy title similarity within a configurable time window.
3. Build clusters, pick a canonical representative, count cross-source refs.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Optional

from rapidfuzz import fuzz

from config import DEDUPE_TIME_WINDOW_HOURS, DEDUPE_TITLE_THRESHOLD
from models import NormalizedStory, StoryCluster
from utils.time import ensure_utc

logger = logging.getLogger(__name__)


def deduplicate(stories: list[NormalizedStory]) -> list[StoryCluster]:
    """Return a list of ``StoryCluster`` objects after merging near-duplicates."""
    if not stories:
        return []

    clusters: list[_Cluster] = []

    for story in stories:
        matched = _find_cluster(story, clusters)
        if matched is not None:
            matched.add(story)
        else:
            clusters.append(_Cluster(story))

    result = [c.to_model() for c in clusters]
    logger.info(
        "Dedupe: %d stories → %d clusters (merged %d duplicates)",
        len(stories), len(result), len(stories) - len(result),
    )
    return result


class _Cluster:
    """Internal mutable cluster builder."""

    def __init__(self, seed: NormalizedStory) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.members: list[NormalizedStory] = [seed]

    @property
    def canonical(self) -> NormalizedStory:
        return max(self.members, key=lambda s: s.source_priority)

    def add(self, story: NormalizedStory) -> None:
        self.members.append(story)

    def to_model(self) -> StoryCluster:
        canonical = self.canonical
        count = len({m.source for m in self.members})
        canonical.dedupe_cluster_id = self.id
        canonical.cross_source_count = count

        return StoryCluster(
            cluster_id=self.id,
            canonical_story=canonical,
            all_sources=[
                {"source": m.source, "url": m.url, "title": m.title}
                for m in self.members
            ],
            cross_source_count=count,
        )


def _find_cluster(story: NormalizedStory, clusters: list[_Cluster]) -> Optional[_Cluster]:
    for cluster in clusters:
        for member in cluster.members:
            if _is_duplicate(story, member):
                return cluster
    return None


def _is_duplicate(a: NormalizedStory, b: NormalizedStory) -> bool:
    # Exact canonical URL match
    if a.canonical_url and a.canonical_url == b.canonical_url:
        return True

    # Fuzzy title match within time window
    title_score = fuzz.token_sort_ratio(a.title.lower(), b.title.lower())
    if title_score < DEDUPE_TITLE_THRESHOLD:
        return False

    if not _within_time_window(a, b):
        return False

    return True


def _within_time_window(a: NormalizedStory, b: NormalizedStory) -> bool:
    if a.published_at is None or b.published_at is None:
        return True  # can't rule it out, allow clustering
    delta = abs((ensure_utc(a.published_at) - ensure_utc(b.published_at)).total_seconds())
    return delta <= DEDUPE_TIME_WINDOW_HOURS * 3600
