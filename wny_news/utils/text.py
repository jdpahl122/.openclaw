"""Text and URL normalisation helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Query parameters typically used for tracking, safe to strip
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "ocid", "ncid", "cmpid",
}


def normalise_url(url: str) -> str:
    """Strip tracking query params and trailing slashes for dedup comparison."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=False)
    cleaned = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
    new_query = urlencode(cleaned, doseq=True) if cleaned else ""
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        path,
        parsed.params,
        new_query,
        "",  # drop fragment
    ))


def story_id(source: str, url: str) -> str:
    """Deterministic short ID from source + canonical URL."""
    digest = hashlib.sha256(f"{source}:{normalise_url(url)}".encode()).hexdigest()[:12]
    return f"{source}-{digest}"


_WHITESPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    return _WHITESPACE.sub(" ", text).strip()


def truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def first_sentences(text: str, n: int = 2) -> str:
    """Extract the first *n* sentences from *text*."""
    sentences: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", text):
        sentences.append(part)
        if len(sentences) >= n:
            break
    return " ".join(sentences)


def strip_html(html: str) -> str:
    """Rough HTML tag stripper (for snippet extraction, not rendering)."""
    return re.sub(r"<[^>]+>", " ", html).strip()
