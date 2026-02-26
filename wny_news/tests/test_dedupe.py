"""Tests for story deduplication / clustering."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dedupe import deduplicate
from models import NormalizedStory, Topic


def _story(
    *,
    source: str = "wgrz",
    title: str = "Test Story",
    url: str = "https://example.com/story",
    canonical_url: str | None = None,
    published_at: datetime | None = None,
    topic: Topic = Topic.NEWS,
) -> NormalizedStory:
    return NormalizedStory(
        id=f"{source}-test",
        source=source,
        source_priority=0.8,
        title=title,
        url=url,
        canonical_url=canonical_url or url,
        published_at=published_at or datetime.now(timezone.utc),
        topic=topic,
    )


class TestDedupe:
    def test_exact_url_match_clusters(self):
        a = _story(source="wgrz", title="Bills Win", url="https://example.com/bills-win")
        b = _story(source="wkbw", title="Bills Win!", url="https://example.com/bills-win")
        clusters = deduplicate([a, b])
        assert len(clusters) == 1
        assert clusters[0].cross_source_count == 2

    def test_fuzzy_title_clusters(self):
        now = datetime.now(timezone.utc)
        a = _story(
            source="wgrz",
            title="Buffalo Bills defeat Miami Dolphins 24-17",
            url="https://wgrz.com/bills-win",
            published_at=now,
        )
        b = _story(
            source="wkbw",
            title="Bills defeat Dolphins 24-17 in Buffalo",
            url="https://wkbw.com/bills-victory",
            published_at=now + timedelta(minutes=30),
        )
        clusters = deduplicate([a, b])
        assert len(clusters) == 1

    def test_different_stories_stay_separate(self):
        a = _story(source="wgrz", title="Snow storm hits Western New York",
                    url="https://wgrz.com/snow")
        b = _story(source="wgrz", title="Bills trade for new quarterback",
                    url="https://wgrz.com/bills-trade")
        clusters = deduplicate([a, b])
        assert len(clusters) == 2

    def test_time_window_respected(self):
        now = datetime.now(timezone.utc)
        a = _story(
            source="wgrz",
            title="Mayor announces new park",
            url="https://wgrz.com/park-a",
            published_at=now,
        )
        b = _story(
            source="wkbw",
            title="Mayor announces new park in Buffalo",
            url="https://wkbw.com/park-b",
            published_at=now - timedelta(hours=48),  # outside default 24h window
        )
        clusters = deduplicate([a, b])
        assert len(clusters) == 2

    def test_empty_input(self):
        assert deduplicate([]) == []

    def test_single_story(self):
        a = _story()
        clusters = deduplicate([a])
        assert len(clusters) == 1
        assert clusters[0].cross_source_count == 1
