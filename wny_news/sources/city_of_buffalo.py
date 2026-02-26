"""City of Buffalo official news – CivicEngage / CivicPlus platform.

Tier 1 source; RSS-first.  Marked as an official source so civic notices
(closures, advisories, meetings) get an authority boost.
"""

from __future__ import annotations

import logging

from config import RSS_FEEDS
from models import RawStory
from sources.base import BaseAdapter

logger = logging.getLogger(__name__)


class CityOfBuffaloAdapter(BaseAdapter):
    name = "city_of_buffalo"

    def fetch(self) -> list[RawStory]:
        feeds = RSS_FEEDS.get(self.name, {})
        stories: list[RawStory] = []
        for section, url in feeds.items():
            try:
                items = self.fetch_rss(url, section=section)
                for item in items:
                    item.tags.append("official")
                stories.extend(items)
            except Exception as exc:
                logger.error("[%s] section=%s error: %s", self.name, section, exc)
        return stories
