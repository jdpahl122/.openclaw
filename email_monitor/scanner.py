"""Fetch unread emails from Gmail via the gog CLI."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import config

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Parsed representation of a single Gmail message."""

    msg_id: str
    thread_id: str
    subject: str = ""
    sender: str = ""
    sender_email: str = ""
    to: str = ""
    date: Optional[datetime] = None
    snippet: str = ""
    body_plain: str = ""
    labels: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    has_attachments: bool = False
    is_reply: bool = False

    @property
    def gmail_url(self) -> str:
        return f"https://mail.google.com/mail/u/0/#inbox/{self.msg_id}"

    @property
    def sender_domain(self) -> str:
        email = self.sender_email.lower()
        return email.split("@")[1] if "@" in email else ""


def _run_gog(*args: str, timeout: int = 30) -> Optional[str]:
    """Run a gog CLI command and return stdout, or None on failure."""
    cmd = [config.GOG_BIN] + list(args)
    if config.GOG_ACCOUNT:
        cmd.extend(["--account", config.GOG_ACCOUNT])
    cmd.append("--json")

    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("gog failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.warning("gog timed out after %ds: %s", timeout, " ".join(cmd))
        return None
    except FileNotFoundError:
        logger.error("gog binary not found at %s", config.GOG_BIN)
        return None


def fetch_unread(max_results: int = 25, query: str = "") -> list[EmailMessage]:
    """Fetch unread messages from the inbox.

    Two-phase: search returns lightweight stubs, then we fetch full details
    for each message to get headers, body, etc.
    """
    q = "in:inbox is:unread"
    if query:
        q += f" {query}"

    raw = _run_gog(
        "gmail", "messages", "search", q, "--max", str(max_results),
    )
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse gog search output: %s", exc)
        return []

    items = data.get("messages") if isinstance(data, dict) else data
    if not items:
        logger.info("No unread messages found")
        return []

    messages: list[EmailMessage] = []
    for item in items:
        msg_id = item.get("id", "")
        if not msg_id:
            continue

        stub = _parse_search_stub(item)
        full = fetch_message(msg_id)
        messages.append(full if full else stub)

    logger.info("Fetched %d unread messages", len(messages))
    return messages


def fetch_message(msg_id: str) -> Optional[EmailMessage]:
    """Fetch a single message by ID with full body via `gog gmail get`."""
    raw = _run_gog("gmail", "get", msg_id)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return _parse_full_message(data)


def _parse_search_stub(item: dict) -> EmailMessage:
    """Parse a lightweight search-result stub into an EmailMessage.

    Search results only have id, threadId, date, from, subject, labels.
    """
    sender_raw = item.get("from", "")
    subject = item.get("subject", "")
    return EmailMessage(
        msg_id=item.get("id", ""),
        thread_id=item.get("threadId", ""),
        subject=subject,
        sender=_extract_name(sender_raw) or sender_raw,
        sender_email=_extract_email(sender_raw),
        labels=item.get("labels", []),
        is_reply=subject.lower().startswith(("re:", "fwd:")),
    )


def _parse_full_message(data: dict) -> Optional[EmailMessage]:
    """Parse a full `gog gmail get` response into an EmailMessage.

    Shape: {body, headers: {from, to, subject, date, cc, bcc}, message: {id, labelIds, ...}}
    """
    msg_obj = data.get("message", {})
    msg_id = msg_obj.get("id", data.get("id", ""))
    if not msg_id:
        return None

    thread_id = msg_obj.get("threadId", data.get("threadId", ""))

    top_headers = data.get("headers", {})
    if isinstance(top_headers, dict):
        headers = {k.lower(): v for k, v in top_headers.items()}
    else:
        headers = {}

    payload_headers_list = msg_obj.get("payload", {}).get("headers", [])
    payload_headers: dict[str, str] = {}
    if isinstance(payload_headers_list, list):
        for h in payload_headers_list:
            payload_headers[h.get("name", "").lower()] = h.get("value", "")

    subject = headers.get("subject", payload_headers.get("subject", ""))
    sender_raw = headers.get("from", payload_headers.get("from", ""))
    to_raw = headers.get("to", payload_headers.get("to", ""))
    date_str = headers.get("date", payload_headers.get("date", ""))

    sender_email = _extract_email(sender_raw)
    sender_name = _extract_name(sender_raw)

    body = data.get("body", "")
    if isinstance(body, dict):
        body = body.get("plain", body.get("text", ""))
    body = body or ""

    # Strip HTML if body is HTML
    if body.lstrip().startswith("<"):
        from html.parser import HTMLParser
        import io

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._parts: list[str] = []
            def handle_data(self, d: str):
                self._parts.append(d)
            def get_text(self) -> str:
                return " ".join(self._parts)

        extractor = _TextExtractor()
        try:
            extractor.feed(body[:10000])
            body = extractor.get_text()
        except Exception:
            pass

    labels = msg_obj.get("labelIds", data.get("labels", []))
    if isinstance(labels, str):
        labels = [labels]

    in_reply_to = payload_headers.get("in-reply-to", "")
    is_reply = bool(in_reply_to) or subject.lower().startswith(("re:", "fwd:"))

    has_attachments = False
    payload = msg_obj.get("payload", {})
    for part in payload.get("parts", []):
        if part.get("filename"):
            has_attachments = True
            break

    dt = None
    if date_str:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str).astimezone(timezone.utc)
        except Exception:
            pass

    return EmailMessage(
        msg_id=msg_id,
        thread_id=thread_id,
        subject=subject,
        sender=sender_name or sender_raw,
        sender_email=sender_email,
        to=to_raw,
        date=dt,
        snippet=msg_obj.get("snippet", ""),
        body_plain=body[:5000],
        labels=labels,
        headers={**payload_headers, **headers},
        has_attachments=has_attachments,
        is_reply=is_reply,
    )


def _extract_email(sender: str) -> str:
    """Extract email address from 'Name <email>' format."""
    if "<" in sender and ">" in sender:
        return sender.split("<")[1].split(">")[0].strip().lower()
    return sender.strip().lower()


def _extract_name(sender: str) -> str:
    """Extract display name from 'Name <email>' format."""
    if "<" in sender:
        return sender.split("<")[0].strip().strip('"').strip("'")
    return ""
