"""Configuration for the Gmail email monitor."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(_PROJECT_DIR / ".env")

# ---------------------------------------------------------------------------
# Gmail / gog
# ---------------------------------------------------------------------------
GOG_ACCOUNT: str = os.getenv("GOG_ACCOUNT", "")
GOG_BIN: str = os.getenv("GOG_BIN", shutil.which("gog") or "gog")

# ---------------------------------------------------------------------------
# Scan window
# ---------------------------------------------------------------------------
INITIAL_LOOKBACK_HOURS: int = int(os.getenv("INITIAL_LOOKBACK_HOURS", "24"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR: Path = _PROJECT_DIR / "data"
STATE_FILE: Path = DATA_DIR / "state.json"

# ---------------------------------------------------------------------------
# Classification: sender domains known to be bulk / marketing
# ---------------------------------------------------------------------------
BULK_SENDER_DOMAINS: set[str] = {
    "mailchimp.com", "mail.mailchimp.com",
    "hubspot.com", "hubspotmail.com",
    "sendgrid.net", "sendgrid.com",
    "constantcontact.com",
    "mailgun.org", "mailgun.net",
    "amazonses.com",
    "salesforce.com", "exacttarget.com",
    "marketo.com", "mktomail.com",
    "pardot.com",
    "intercom.io", "intercommail.com",
    "drip.com",
    "convertkit.com",
    "klaviyo.com",
    "beehiiv.com",
    "substack.com", "substackmail.com",
    "linkedin.com",
    "facebookmail.com",
    "noreply.github.com",
    "accounts.google.com",
}

# Sender local-parts that signal automated / no-reply
NOREPLY_PATTERNS: list[str] = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications", "notification", "mailer-daemon",
    "postmaster", "bounce", "auto-confirm",
]

# ---------------------------------------------------------------------------
# Classification: subject keywords
# ---------------------------------------------------------------------------
SALES_KEYWORDS: list[str] = [
    "unsubscribe", "limited time", "% off", "free trial",
    "act now", "exclusive offer", "don't miss", "last chance",
    "flash sale", "promo code", "coupon", "discount",
    "webinar", "join us for", "register now",
]

NEWSLETTER_KEYWORDS: list[str] = [
    "newsletter", "digest", "weekly update", "monthly update",
    "roundup", "recap", "this week in", "top stories",
]

# ---------------------------------------------------------------------------
# Classification: positive signals that email needs a response
# ---------------------------------------------------------------------------
RESPONSE_KEYWORDS: list[str] = [
    "?",  # questions
    "please", "could you", "can you", "would you",
    "let me know", "get back to", "your thoughts",
    "attached", "invoice", "proposal", "quote",
    "meeting", "schedule", "call",
    "urgent", "asap", "priority",
]

# ---------------------------------------------------------------------------
# Scoring weights (heuristic classifier)
# ---------------------------------------------------------------------------
SCORING_WEIGHTS: dict[str, float] = {
    "bulk_sender": -0.60,
    "noreply_sender": -0.40,
    "list_unsubscribe_header": -0.50,
    "sales_keyword": -0.15,       # per keyword match (capped)
    "newsletter_keyword": -0.30,
    "response_keyword": 0.10,     # per keyword match (capped)
    "is_reply": 0.25,             # Re: / Fwd: or in-reply-to present
    "short_body": 0.10,           # personal emails tend to be shorter
    "direct_to": 0.15,            # To: is the user, not BCC / mailing list
}

# Threshold: score >= this → needs_response; below → skip
RESPONSE_THRESHOLD: float = 0.0

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
CATEGORY_NEEDS_RESPONSE = "needs_response"
CATEGORY_INFORMATIONAL = "informational"
CATEGORY_NEWSLETTER = "newsletter"
CATEGORY_SALES = "sales"
CATEGORY_AUTOMATED = "automated"

# ---------------------------------------------------------------------------
# Priority levels & thresholds
# ---------------------------------------------------------------------------
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"

PRIORITY_HIGH_THRESHOLD: float = 0.40
PRIORITY_MEDIUM_THRESHOLD: float = 0.10

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("EMAIL_MONITOR_LOG_LEVEL", "INFO")
