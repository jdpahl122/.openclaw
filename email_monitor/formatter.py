"""Format classified emails into a Telegram-friendly digest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import config
from classifier import Classification
from scanner import EmailMessage

_PRIORITY_ICONS = {
    config.PRIORITY_HIGH: "🔴",
    config.PRIORITY_MEDIUM: "🟡",
    config.PRIORITY_LOW: "🟢",
}


def format_digest(
    classified: list[tuple[EmailMessage, Classification]],
    now: Optional[datetime] = None,
) -> str:
    """Produce a Markdown digest suitable for Telegram delivery.

    Groups emails into NEEDS RESPONSE and SKIPPED sections,
    with priority badges and body summaries.
    """
    if not classified:
        return ""

    now = now or datetime.now(timezone.utc)

    actionable = [
        (msg, cls) for msg, cls in classified if cls.needs_response
    ]
    skipped = [
        (msg, cls) for msg, cls in classified if cls.is_skippable
    ]
    informational = [
        (msg, cls) for msg, cls in classified
        if cls.category == config.CATEGORY_INFORMATIONAL
    ]

    actionable.sort(key=lambda x: _priority_sort_key(x[1].priority))

    total = len(classified)
    lines: list[str] = []
    lines.append(f"📬 Inbox Summary ({total} new since last check)")
    lines.append("")

    if actionable:
        lines.append(f"⚡ NEEDS RESPONSE ({len(actionable)}):")
        lines.append("")
        for i, (msg, cls) in enumerate(actionable, 1):
            lines.append(_format_actionable(i, msg, cls, now))
            lines.append("")

    if informational:
        lines.append(f"ℹ️ INFORMATIONAL ({len(informational)}):")
        lines.append("")
        for i, (msg, cls) in enumerate(informational, 1):
            lines.append(_format_informational(i, msg, cls, now))
            lines.append("")

    if skipped:
        label_parts = []
        sales_count = sum(1 for _, c in skipped if c.category == config.CATEGORY_SALES)
        news_count = sum(1 for _, c in skipped if c.category == config.CATEGORY_NEWSLETTER)
        auto_count = sum(1 for _, c in skipped if c.category == config.CATEGORY_AUTOMATED)
        if sales_count:
            label_parts.append(f"{sales_count} sales")
        if news_count:
            label_parts.append(f"{news_count} newsletter")
        if auto_count:
            label_parts.append(f"{auto_count} automated")
        label = "/".join(label_parts) if label_parts else "skipped"
        lines.append(f"🗑 SKIPPED ({len(skipped)} {label}):")
        for msg, cls in skipped:
            lines.append(f"  - {_safe_sender(msg)} — \"{msg.subject[:60]}\"")
        lines.append("")

    lines.append("Reply with context to draft a response, e.g.:")
    lines.append('"Draft a reply to John Smith -- tell him we\'ll have the timeline by Friday"')

    return "\n".join(lines)


def _format_actionable(idx: int, msg: EmailMessage, cls: Classification, now: datetime) -> str:
    icon = _PRIORITY_ICONS.get(cls.priority, "⚪")
    ago = _time_ago(msg.date, now)
    parts = [
        f"{idx}. {icon} [{cls.priority}] {_safe_sender(msg)}",
        f"   Subject: {msg.subject[:80]}",
        f"   Received: {ago}",
    ]
    if cls.summary:
        parts.append(f"   Summary: {cls.summary}")
    parts.append(f"   {msg.gmail_url}")
    return "\n".join(parts)


def _format_informational(idx: int, msg: EmailMessage, cls: Classification, now: datetime) -> str:
    ago = _time_ago(msg.date, now)
    parts = [f"{idx}. {_safe_sender(msg)} — \"{msg.subject[:60]}\" ({ago})"]
    if cls.summary:
        parts.append(f"   Summary: {cls.summary}")
    return "\n".join(parts)


def _safe_sender(msg: EmailMessage) -> str:
    """Format sender for display, avoiding empty strings."""
    if msg.sender and msg.sender_email:
        return f"{msg.sender} <{msg.sender_email}>"
    return msg.sender_email or msg.sender or "(unknown)"


def _priority_sort_key(priority: str) -> int:
    return {config.PRIORITY_HIGH: 0, config.PRIORITY_MEDIUM: 1, config.PRIORITY_LOW: 2}.get(priority, 3)


def _time_ago(dt: Optional[datetime], now: datetime) -> str:
    if not dt:
        return "unknown time"
    delta = now - dt
    minutes = int(delta.total_seconds() / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"
