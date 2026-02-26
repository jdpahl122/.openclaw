"""HTTP utilities with retry, timeout, and User-Agent support."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import HTTP_RETRIES, HTTP_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=HTTP_RETRIES,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _build_session()
    return _session


def fetch_url(url: str, *, timeout: int = HTTP_TIMEOUT) -> Optional[str]:
    """Fetch *url* and return the response body as text, or None on failure."""
    session = get_session()
    t0 = time.monotonic()
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        elapsed = (time.monotonic() - t0) * 1000
        logger.debug("Fetched %s in %.0f ms (%d bytes)", url, elapsed, len(resp.text))
        return resp.text
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - t0) * 1000
        logger.warning("Failed to fetch %s after %.0f ms: %s", url, elapsed, exc)
        return None


def fetch_bytes(url: str, *, timeout: int = HTTP_TIMEOUT) -> Optional[bytes]:
    """Fetch *url* and return raw bytes, or None on failure."""
    session = get_session()
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as exc:
        logger.warning("Failed to fetch bytes from %s: %s", url, exc)
        return None
