"""Heuristic email classifier with optional LLM prompt template."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import config
from scanner import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class Classification:
    """Classification result for an email."""

    category: str
    score: float
    reasons: list[str]
    priority: str = config.PRIORITY_LOW
    summary: str = ""

    @property
    def needs_response(self) -> bool:
        return self.category == config.CATEGORY_NEEDS_RESPONSE

    @property
    def is_skippable(self) -> bool:
        return self.category in (
            config.CATEGORY_SALES,
            config.CATEGORY_NEWSLETTER,
            config.CATEGORY_AUTOMATED,
        )


def _extract_summary(msg: EmailMessage, max_len: int = 200) -> str:
    """Build a brief summary from the email body and snippet."""
    text = msg.body_plain.strip()
    if not text:
        text = msg.snippet.strip()
    if not text:
        return ""

    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text[:1500])
    summary_parts: list[str] = []
    length = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if length + len(s) > max_len and summary_parts:
            break
        summary_parts.append(s)
        length += len(s)
    return " ".join(summary_parts)[:max_len].strip()


def _assign_priority(score: float, msg: EmailMessage) -> str:
    """Derive priority from score and urgency signals."""
    subject_lower = msg.subject.lower()
    body_lower = (msg.body_plain[:1000]).lower()
    combined = f"{subject_lower} {body_lower}"

    urgent_signals = ["urgent", "asap", "time-sensitive", "immediate", "critical", "emergency"]
    has_urgency = any(kw in combined for kw in urgent_signals)

    if has_urgency:
        return config.PRIORITY_HIGH
    if score >= config.PRIORITY_HIGH_THRESHOLD:
        return config.PRIORITY_HIGH
    if score >= config.PRIORITY_MEDIUM_THRESHOLD:
        return config.PRIORITY_MEDIUM
    return config.PRIORITY_LOW


def classify(msg: EmailMessage) -> Classification:
    """Classify a single email using heuristic scoring."""
    score = 0.0
    reasons: list[str] = []

    # --- Negative signals (bulk / marketing / automated) ---

    if msg.sender_domain in config.BULK_SENDER_DOMAINS:
        score += config.SCORING_WEIGHTS["bulk_sender"]
        reasons.append(f"bulk sender domain: {msg.sender_domain}")

    local_part = msg.sender_email.split("@")[0].lower() if "@" in msg.sender_email else ""
    if any(pat in local_part for pat in config.NOREPLY_PATTERNS):
        score += config.SCORING_WEIGHTS["noreply_sender"]
        reasons.append(f"noreply sender: {local_part}")

    if "list-unsubscribe" in msg.headers:
        score += config.SCORING_WEIGHTS["list_unsubscribe_header"]
        reasons.append("has List-Unsubscribe header")

    subject_lower = msg.subject.lower()
    body_preview = (msg.body_plain[:2000] + " " + msg.snippet).lower()
    combined_text = f"{subject_lower} {body_preview}"

    sales_hits = sum(1 for kw in config.SALES_KEYWORDS if kw in combined_text)
    if sales_hits:
        penalty = min(sales_hits, 4) * config.SCORING_WEIGHTS["sales_keyword"]
        score += penalty
        reasons.append(f"sales keywords ({sales_hits} hits)")

    newsletter_hits = sum(1 for kw in config.NEWSLETTER_KEYWORDS if kw in combined_text)
    if newsletter_hits:
        score += config.SCORING_WEIGHTS["newsletter_keyword"]
        reasons.append(f"newsletter keywords ({newsletter_hits} hits)")

    # --- Positive signals (personal / actionable) ---

    response_hits = sum(1 for kw in config.RESPONSE_KEYWORDS if kw in combined_text)
    if response_hits:
        boost = min(response_hits, 5) * config.SCORING_WEIGHTS["response_keyword"]
        score += boost
        reasons.append(f"response keywords ({response_hits} hits)")

    if msg.is_reply:
        score += config.SCORING_WEIGHTS["is_reply"]
        reasons.append("is a reply/forward")

    body_len = len(msg.body_plain)
    if 0 < body_len < 2000:
        score += config.SCORING_WEIGHTS["short_body"]
        reasons.append("short body (likely personal)")

    if config.GOG_ACCOUNT and config.GOG_ACCOUNT.lower() in msg.to.lower():
        score += config.SCORING_WEIGHTS["direct_to"]
        reasons.append("directly addressed to user")

    category = _score_to_category(score, reasons)
    priority = _assign_priority(score, msg)
    summary = _extract_summary(msg)

    logger.debug(
        "Classified [%s] score=%.2f category=%s priority=%s: %s",
        msg.subject[:50], score, category, priority, "; ".join(reasons),
    )

    return Classification(
        category=category, score=score, reasons=reasons,
        priority=priority, summary=summary,
    )


def _score_to_category(score: float, reasons: list[str]) -> str:
    """Map a numeric score to a category label."""
    has_bulk = any("bulk sender" in r for r in reasons)
    has_noreply = any("noreply sender" in r for r in reasons)
    has_newsletter = any("newsletter" in r for r in reasons)
    has_sales = any("sales keywords" in r for r in reasons)

    if score >= config.RESPONSE_THRESHOLD:
        return config.CATEGORY_NEEDS_RESPONSE

    if has_newsletter and not has_sales:
        return config.CATEGORY_NEWSLETTER

    if has_sales:
        return config.CATEGORY_SALES

    if has_noreply or has_bulk:
        return config.CATEGORY_AUTOMATED

    return config.CATEGORY_INFORMATIONAL


# ---------------------------------------------------------------------------
# LLM prompt builder (for future upgrade)
# ---------------------------------------------------------------------------

def build_llm_prompt(msg: EmailMessage, heuristic: Classification) -> str:
    """Build a prompt for an LLM to classify / summarise the email.

    This is an abstracted template -- no API keys or model references.
    The calling code can pass this to whatever LLM backend is available.
    """
    return f"""Classify this email and provide a one-line summary.

From: {msg.sender} <{msg.sender_email}>
To: {msg.to}
Subject: {msg.subject}
Date: {msg.date}
Is Reply: {msg.is_reply}
Has Attachments: {msg.has_attachments}

Body (first 1500 chars):
{msg.body_plain[:1500]}

---
Heuristic pre-classification: {heuristic.category} (score: {heuristic.score:.2f})
Reasons: {'; '.join(heuristic.reasons)}

Please respond with JSON:
{{
  "category": "needs_response" | "informational" | "newsletter" | "sales" | "automated",
  "confidence": 0.0-1.0,
  "summary": "one line summary",
  "suggested_action": "reply" | "read" | "archive" | "ignore"
}}"""
