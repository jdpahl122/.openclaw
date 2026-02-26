"""Tests for story ranking / scoring."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import NormalizedStory, StoryCluster, Topic
from ranking import rank_clusters


def _cluster(
    *,
    source: str = "wgrz",
    title: str = "Test",
    topic: Topic = Topic.NEWS,
    published_at: datetime | None = None,
    cross_source_count: int = 1,
    is_official: bool = False,
) -> StoryCluster:
    now = datetime.now(timezone.utc)
    story = NormalizedStory(
        id=f"{source}-{title[:6]}",
        source=source,
        source_priority=0.8,
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        canonical_url=f"https://example.com/{title.lower().replace(' ', '-')}",
        published_at=published_at or now,
        topic=topic,
        is_official_source=is_official,
    )
    return StoryCluster(
        cluster_id=story.id,
        canonical_story=story,
        all_sources=[{"source": source, "url": story.url, "title": title}],
        cross_source_count=cross_source_count,
    )


class TestRanking:
    def test_recent_beats_old(self):
        now = datetime.now(timezone.utc)
        recent = _cluster(title="Recent Story", published_at=now)
        old = _cluster(title="Old Story", published_at=now - timedelta(hours=48))
        ranked = rank_clusters([old, recent])
        assert ranked[0].title == "Recent Story"

    def test_multi_source_boost(self):
        now = datetime.now(timezone.utc)
        single = _cluster(title="Single Source", published_at=now, cross_source_count=1)
        multi = _cluster(title="Multi Source", published_at=now, cross_source_count=3)
        ranked = rank_clusters([single, multi])
        assert ranked[0].title == "Multi Source"

    def test_official_source_boost(self):
        now = datetime.now(timezone.utc)
        regular = _cluster(title="Regular", source="wgrz", published_at=now)
        official = _cluster(
            title="Official Notice", source="city_of_buffalo",
            topic=Topic.CIVIC, published_at=now, is_official=True,
        )
        ranked = rank_clusters([regular, official])
        assert ranked[0].title == "Official Notice"

    def test_sports_topic_filter(self):
        now = datetime.now(timezone.utc)
        news = _cluster(title="Generic News", topic=Topic.NEWS, published_at=now)
        sports = _cluster(title="Bills Win Superbowl", topic=Topic.SPORTS, published_at=now)
        ranked = rank_clusters([news, sports], topic_filter="sports")
        assert len(ranked) == 1
        assert ranked[0].topic == Topic.SPORTS

    def test_scores_are_bounded(self):
        c = _cluster(title="Test", cross_source_count=5)
        ranked = rank_clusters([c])
        assert 0.0 <= ranked[0].score <= 1.0

    def test_topic_classification_bills(self):
        """Bills keyword should produce a sports boost score > 0."""
        c = _cluster(title="Buffalo Bills sign free agent linebacker")
        ranked = rank_clusters([c])
        assert ranked[0].debug_scores.get("sports_boost", 0) > 0
