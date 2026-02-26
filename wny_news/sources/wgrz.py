"""WGRZ (Channel 2 Buffalo) – TEGNA station.

Tier 1 source; RSS-first.  Feeds follow the pattern
``/feeds/syndication/rss/<section>``.
"""

from __future__ import annotations

import logging

from config import RSS_FEEDS
from models import RawStory
from sources.base import BaseAdapter

logger = logging.getLogger(__name__)


class WGRZAdapter(BaseAdapter):
    name = "wgrz"

    def fetch(self) -> list[RawStory]:
        feeds = RSS_FEEDS.get(self.name, {})
        stories: list[RawStory] = []
        for section, url in feeds.items():
            try:
                stories.extend(self.fetch_rss(url, section=section))
            except Exception as exc:
                logger.error("[%s] section=%s error: %s", self.name, section, exc)
        return stories
