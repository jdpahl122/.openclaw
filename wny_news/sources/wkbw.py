"""WKBW (7 News Buffalo) – Scripps station.

Tier 2 source; HTML scraper fallback.  WKBW's RSS availability is
inconsistent, so we scrape article listing pages.
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


class WKBWAdapter(BaseAdapter):
    name = "wkbw"

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

        # WKBW (Scripps) typically renders article cards as <article> or
        # <div class="...card..."> with <a> and <h*> children.
        # This parser targets common patterns; may need tuning if layout changes.
        for card in soup.select("article, .story-card, .card-content"):
            link_el = card.find("a", href=True)
            if not link_el:
                continue
            href: str = link_el["href"]
            if not href.startswith("http"):
                href = f"https://www.wkbw.com{href}"

            title_el = card.find(["h1", "h2", "h3", "h4"])
            title = clean_text(title_el.get_text()) if title_el else clean_text(link_el.get_text())
            if not title:
                continue

            snippet = self._extract_snippet(card)
            pub_date = self._extract_date(card)

            stories.append(RawStory(
                source=self.name,
                adapter="html",
                title=title,
                url=href,
                published_at=pub_date,
                section=section,
                snippet=snippet,
                fetch_metadata={"page_url": url},
            ))

        logger.info("[%s] HTML %s → %d items", self.name, url, len(stories))
        return stories

    @staticmethod
    def _extract_snippet(card) -> Optional[str]:
        for sel in (".description", ".summary", "p"):
            el = card.select_one(sel)
            if el:
                return clean_text(el.get_text())
        return None

    @staticmethod
    def _extract_date(card) -> Optional[str]:
        time_el = card.find("time")
        if time_el:
            return parse_flexible(time_el.get("datetime", time_el.get_text()))
        return None
