"""Structured logging setup for the WNY news tool."""

from __future__ import annotations

import logging
import sys

from config import LOG_LEVEL

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """Configure root logger with a concise format."""
    effective = (level or LOG_LEVEL).upper()
    logging.basicConfig(
        level=getattr(logging, effective, logging.INFO),
        format=_FORMAT,
        datefmt=_DATE_FMT,
        stream=sys.stderr,
        force=True,
    )
    # Quiet noisy third-party loggers
    for name in ("urllib3", "requests", "feedparser", "chardet"):
        logging.getLogger(name).setLevel(logging.WARNING)
