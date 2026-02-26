"""WGR 550 – Buffalo sports talk radio (Audacy).

Tier 2 source; HTML scraper.
"""

from __future__ import annotations

import logging
from typing import Optional

from bs4 import BeautifulSoup

from config import HTML_SOURCES
from models import RawStory
from sources.base import BaseAdapter
from utils.http import fetch_url
from utils.text import clean_text
from utils.time import parse_flexible

logger = logging.getLogger(__name__)


class WGR550Adapter(BaseAdapter):
    name = "wgr550"

    def fetch(self) -> list[RawStory]:
        pages = HTML_SOURCES.get(self.name, {})
        stories: list[RawStory] = []
        for section, url in pages.items():
            try:
                items = self._scrape_listing(url, section)
                stories.extend(items)
            except Exception as exc:
                logger.error("[%s] section=%s error: %s", self.name, section, exc)
        return stories

    def _scrape_listing(self, url: str, section: str) -> list[RawStory]:
        html = fetch_url(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        stories: list[RawStory] = []

        # Audacy renders article cards; selectors are best-effort since the
        # site uses React hydration and may not render all content in initial HTML.
        for card in soup.select("article, .content-card, [data-testid='content-card'], .topic-card"):
            link_el = card.find("a", href=True)
            if not link_el:
                continue
            href: str = link_el["href"]
            if not href.startswith("http"):
                href = f"https://www.audacy.com{href}"

            title_el = card.find(["h1", "h2", "h3", "h4"])
            title = clean_text(title_el.get_text()) if title_el else clean_text(link_el.get_text())
            if not title:
                continue

            snippet: Optional[str] = None
            p = card.find("p")
            if p:
                snippet = clean_text(p.get_text())

            pub_date = None
            time_el = card.find("time")
            if time_el:
                pub_date = parse_flexible(time_el.get("datetime", time_el.get_text()))

            stories.append(RawStory(
                source=self.name,
                adapter="html",
                title=title,
                url=href,
                published_at=pub_date,
                section=section or "sports",
                snippet=snippet,
                tags=["sports"],
                fetch_metadata={"page_url": url},
            ))

        logger.info("[%s] HTML %s → %d items", self.name, url, len(stories))
        return stories
