"""WIVB (News 4 Buffalo) – Nexstar station.

Tier 2 / optional source; RSS-first (WordPress /feed/ endpoint).
Falls back to HTML if RSS returns no items.
"""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from config import HTML_SOURCES, RSS_FEEDS
from models import RawStory
from sources.base import BaseAdapter
from utils.http import fetch_url
from utils.text import clean_text
from utils.time import parse_flexible

logger = logging.getLogger(__name__)


class WIVBAdapter(BaseAdapter):
    name = "wivb"

    def fetch(self) -> list[RawStory]:
        stories = self._try_rss()
        if stories:
            return stories
        logger.info("[%s] RSS returned no items, trying HTML fallback", self.name)
        return self._try_html()

    def _try_rss(self) -> list[RawStory]:
        feeds = RSS_FEEDS.get(self.name, {})
        stories: list[RawStory] = []
        for section, url in feeds.items():
            try:
                stories.extend(self.fetch_rss(url, section=section))
            except Exception as exc:
                logger.error("[%s] RSS section=%s error: %s", self.name, section, exc)
        return stories

    def _try_html(self) -> list[RawStory]:
        # Fallback: scrape the WIVB homepage or news listing
        url = "https://www.wivb.com/news/"
        html = fetch_url(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        stories: list[RawStory] = []

        for card in soup.select("article, .article-list__article"):
            link_el = card.find("a", href=True)
            if not link_el:
                continue
            href = link_el["href"]
            title_el = card.find(["h1", "h2", "h3", "h4"])
            title = clean_text(title_el.get_text()) if title_el else ""
            if not title:
                continue

            pub_date = None
            time_el = card.find("time")
            if time_el:
                pub_date = parse_flexible(time_el.get("datetime", ""))

            stories.append(RawStory(
                source=self.name,
                adapter="html",
                title=title,
                url=href,
                published_at=pub_date,
                section="news",
                fetch_metadata={"page_url": url},
            ))

        logger.info("[%s] HTML fallback → %d items", self.name, len(stories))
        return stories
