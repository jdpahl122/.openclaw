"""Spectrum News 1 Buffalo – Charter Communications.

Tier 1 source; RSS-first.
TODO: verify feed URL -- Spectrum has restructured their web presence.
"""

from __future__ import annotations

import logging

from config import RSS_FEEDS
from models import RawStory
from sources.base import BaseAdapter

logger = logging.getLogger(__name__)


class SpectrumBuffaloAdapter(BaseAdapter):
    name = "spectrum_buffalo"

    def fetch(self) -> list[RawStory]:
        feeds = RSS_FEEDS.get(self.name, {})
        stories: list[RawStory] = []
        for section, url in feeds.items():
            try:
                stories.extend(self.fetch_rss(url, section=section))
            except Exception as exc:
                logger.error("[%s] section=%s error: %s", self.name, section, exc)
        return stories
