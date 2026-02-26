"""Abstract base class for news source adapters.

Every adapter MUST implement ``fetch()`` and return a list of ``RawStory``.
The base class provides common RSS parsing so individual adapters only need
to supply feed URLs and optional post-processing.
"""

from __future__ import annotations

import abc
import logging
import time
from datetime import datetime
from typing import Optional

import feedparser

from models import RawStory
from utils.http import fetch_url
from utils.text import clean_text, strip_html
from utils.time import parse_flexible

logger = logging.getLogger(__name__)


class BaseAdapter(abc.ABC):
    """Interface every source adapter must satisfy."""

    name: str = "unknown"

    @abc.abstractmethod
    def fetch(self) -> list[RawStory]:
        """Return stories from this source.  Must not raise."""
        ...

    # -- RSS convenience --------------------------------------------------------

    def fetch_rss(self, feed_url: str, *, section: str = "") -> list[RawStory]:
        """Fetch and parse an RSS/Atom feed into ``RawStory`` objects."""
        t0 = time.monotonic()
        body = fetch_url(feed_url)
        if body is None:
            logger.warning("[%s] RSS fetch returned nothing for %s", self.name, feed_url)
            return []

        feed = feedparser.parse(body)
        stories: list[RawStory] = []
        for entry in feed.entries:
            title = clean_text(getattr(entry, "title", "") or "")
            if not title:
                continue

            link = getattr(entry, "link", "") or ""
            published = self._entry_date(entry)
            snippet = clean_text(strip_html(getattr(entry, "summary", "") or ""))
            content = self._entry_content(entry)
            author = getattr(entry, "author", None)
            tags = [t.get("term", "") for t in getattr(entry, "tags", []) if t.get("term")]

            stories.append(RawStory(
                source=self.name,
                adapter="rss",
                title=title,
                url=link,
                published_at=published,
                author=author,
                section=section or None,
                snippet=snippet or None,
                content=content or None,
                tags=tags,
                fetch_metadata={"feed_url": feed_url},
            ))

        elapsed = (time.monotonic() - t0) * 1000
        logger.info("[%s] RSS %s → %d items (%.0f ms)", self.name, feed_url, len(stories), elapsed)
        return stories

    # -- helpers ----------------------------------------------------------------

    @staticmethod
    def _entry_date(entry) -> Optional[datetime]:
        for attr in ("published", "updated"):
            raw = getattr(entry, attr, None)
            if raw:
                dt = parse_flexible(raw)
                if dt:
                    return dt
        return None

    @staticmethod
    def _entry_content(entry) -> Optional[str]:
        """Pull the best available full-text content from an RSS entry."""
        contents = getattr(entry, "content", None)
        if contents and isinstance(contents, list):
            for c in contents:
                val = c.get("value", "")
                if val:
                    return clean_text(strip_html(val))
        return None
