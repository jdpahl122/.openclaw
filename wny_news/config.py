"""Centralised configuration for the WNY news tool.

All tuneable knobs live here so adapters, ranking, and dedupe can import
a single module. Override via environment variables or .env file.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(_PROJECT_DIR / ".env")

# ---------------------------------------------------------------------------
# Source priorities  (0.0 – 1.0, higher = more trustworthy / prominent)
# ---------------------------------------------------------------------------
SOURCE_PRIORITIES: dict[str, float] = {
    "wgrz": 0.90,
    "spectrum_buffalo": 0.90,
    "city_of_buffalo": 0.95,
    "ub": 0.75,
    "wkbw": 0.85,
    "wgr550": 0.85,
    "wivb": 0.80,
}

# ---------------------------------------------------------------------------
# Topic priorities
# ---------------------------------------------------------------------------
TOPIC_PRIORITIES: dict[str, float] = {
    "news": 0.80,
    "sports": 0.70,
    "weather": 0.85,
    "traffic": 0.60,
    "civic": 0.90,
    "education": 0.60,
    "other": 0.40,
}

# ---------------------------------------------------------------------------
# WNY sports teams – used for topic classification and score boosting
# ---------------------------------------------------------------------------
SPORTS_TEAMS: dict[str, dict] = {
    "bills": {
        "keywords": ["buffalo bills", "nfl draft", "josh allen", "bills stadium",
                      "bills game", "bills roster", "bills trade"],
        "subtopic": "bills",
        "boost": 0.15,
    },
    "sabres": {
        "keywords": ["sabres", "buffalo sabres", "nhl"],
        "subtopic": "sabres",
        "boost": 0.12,
    },
    "bisons": {
        "keywords": ["bisons", "buffalo bisons"],
        "subtopic": "bisons",
        "boost": 0.08,
    },
    "bandits": {
        "keywords": ["bandits", "buffalo bandits", "nll"],
        "subtopic": "bandits",
        "boost": 0.08,
    },
    "ub_bulls": {
        "keywords": ["ub bulls", "university at buffalo athletics", "ub football",
                      "ub basketball"],
        "subtopic": "ub",
        "boost": 0.06,
    },
}

# ---------------------------------------------------------------------------
# Ranking weights  (should sum to ~1.0 for interpretability)
# ---------------------------------------------------------------------------
RANKING_WEIGHTS: dict[str, float] = {
    "recency": 0.30,
    "source_priority": 0.20,
    "topic_priority": 0.15,
    "sports_boost": 0.10,
    "cross_source_boost": 0.15,
    "official_source_boost": 0.10,
}

# ---------------------------------------------------------------------------
# Dedupe / clustering thresholds
# ---------------------------------------------------------------------------
DEDUPE_TITLE_THRESHOLD: int = 75          # rapidfuzz ratio (0-100)
DEDUPE_TIME_WINDOW_HOURS: int = 24        # stories within this window may cluster

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_HOURS: int = int(os.getenv("WNY_NEWS_DEFAULT_HOURS", "24"))
DEFAULT_TOP_N: int = int(os.getenv("WNY_NEWS_DEFAULT_TOP_N", "10"))

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
HTTP_TIMEOUT: int = int(os.getenv("WNY_NEWS_HTTP_TIMEOUT", "15"))
HTTP_RETRIES: int = 2
USER_AGENT: str = os.getenv(
    "WNY_NEWS_USER_AGENT", "OpenClaw-WNY-News/1.0 (+https://openclaw.ai)"
)

# ---------------------------------------------------------------------------
# RSS feed URLs  –  keyed by source name → section → URL
# Many of these need live verification; marked with TODO where uncertain.
# ---------------------------------------------------------------------------
RSS_FEEDS: dict[str, dict[str, str]] = {
    "wgrz": {
        # TEGNA station; feeds follow /feeds/syndication/rss/<section>
        "news": "https://www.wgrz.com/feeds/syndication/rss/news",
        "sports": "https://www.wgrz.com/feeds/syndication/rss/sports",
    },
    "spectrum_buffalo": {
        # TODO: verify exact Spectrum News 1 Buffalo RSS path
        "news": "https://spectrumlocalnews.com/nys/buffalo/news.rss",
    },
    "city_of_buffalo": {
        # CivicEngage / CivicPlus platform
        # TODO: verify RSS path for buffalony.gov
        "news": "https://www.buffalony.gov/RSSFeed.aspx",
    },
    "ub": {
        "news": "http://www.buffalo.edu/news/rss/national.rss",
        # TODO: find working UB campus news RSS; /ubreporter and /ubnow 404
        # "campus": "http://www.buffalo.edu/ubnow.rss",
        "athletics": "https://ubbulls.com/rss",
    },
    "wivb": {
        # Nexstar / WordPress-based
        "news": "https://www.wivb.com/feed/",
    },
}

# ---------------------------------------------------------------------------
# HTML fallback URLs  (for sources without reliable RSS)
# ---------------------------------------------------------------------------
HTML_SOURCES: dict[str, dict[str, str]] = {
    "wkbw": {
        # Scripps station – RSS availability varies
        "local": "https://www.wkbw.com/news/local-news",
        "sports": "https://www.wkbw.com/sports",
    },
    "wgr550": {
        "sports": "https://www.audacy.com/wgr550/sports",
    },
}

# ---------------------------------------------------------------------------
# Official sources (for is_official_source flag)
# ---------------------------------------------------------------------------
OFFICIAL_SOURCES: set[str] = {"city_of_buffalo"}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = os.getenv("WNY_NEWS_OUTPUT_DIR", str(_PROJECT_DIR / "output"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("WNY_NEWS_LOG_LEVEL", "INFO")
