"""Date/time helpers for the WNY news pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import email.utils


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hours_ago(hours: int) -> datetime:
    return now_utc() - timedelta(hours=hours)


def is_within_window(dt: Optional[datetime], hours: int) -> bool:
    """Return True if *dt* falls within the last *hours* from now."""
    if dt is None:
        return True  # keep stories with unknown dates rather than dropping them
    cutoff = hours_ago(hours)
    aware_dt = ensure_utc(dt)
    return aware_dt >= cutoff


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_rfc2822(date_str: str) -> Optional[datetime]:
    """Parse an RFC-2822 date string (common in RSS) into a UTC datetime."""
    try:
        tup = email.utils.parsedate_to_datetime(date_str)
        return ensure_utc(tup)
    except Exception:
        return None


def parse_iso(date_str: str) -> Optional[datetime]:
    """Parse an ISO-8601 date string into a UTC datetime."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return ensure_utc(dt)
    except Exception:
        return None


def parse_flexible(date_str: Optional[str]) -> Optional[datetime]:
    """Try multiple date formats and return a UTC datetime or None."""
    if not date_str:
        return None
    for parser in (parse_iso, parse_rfc2822):
        result = parser(date_str)
        if result:
            return result
    return None


def relative_age(dt: Optional[datetime]) -> str:
    """Human-readable age like '2h ago' or '3d ago'."""
    if dt is None:
        return "unknown"
    delta = now_utc() - ensure_utc(dt)
    seconds = delta.total_seconds()
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"
