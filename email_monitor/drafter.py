"""Create, read, and send Gmail drafts via the gog CLI."""

from __future__ import annotations

import base64
import html
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_cached_signature: Optional[str] = None


def _run_gog(*args: str, timeout: int = 30) -> Optional[str]:
    """Run a gog CLI command and return stdout, or None on failure."""
    cmd = [config.GOG_BIN] + list(args)
    if config.GOG_ACCOUNT:
        cmd.extend(["--account", config.GOG_ACCOUNT])
    cmd.append("--json")

    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.error("gog failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.error("gog timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        logger.error("gog binary not found at %s", config.GOG_BIN)
        return None


def _fetch_gmail_signature() -> str:
    """Fetch the HTML signature from Gmail sendas settings."""
    global _cached_signature
    if _cached_signature is not None:
        return _cached_signature

    send_as_email = config.GOG_ACCOUNT
    if not send_as_email:
        _cached_signature = ""
        return ""

    raw = _run_gog("gmail", "settings", "sendas", "get", send_as_email)
    if not raw:
        _cached_signature = ""
        return ""

    try:
        data = json.loads(raw)
        sig = data.get("sendAs", {}).get("signature", "")
        _cached_signature = sig
        return sig
    except (json.JSONDecodeError, KeyError):
        _cached_signature = ""
        return ""


def _plain_to_html(text: str) -> str:
    """Convert plain text body to simple HTML, preserving line breaks."""
    escaped = html.escape(text)
    return escaped.replace("\n", "<br>\n")


def create_draft(
    to: str,
    subject: str,
    body: str,
    reply_to_message_id: Optional[str] = None,
) -> Optional[str]:
    """Create a Gmail draft via gog CLI. Returns the draft ID on success."""
    cmd = [config.GOG_BIN, "gmail", "drafts", "create"]
    if config.GOG_ACCOUNT:
        cmd.extend(["--account", config.GOG_ACCOUNT])

    cmd.extend(["--to", to, "--subject", subject])

    if reply_to_message_id:
        cmd.extend(["--reply-to-message-id", reply_to_message_id])

    cmd.extend(["--json", "--no-input"])

    signature_html = _fetch_gmail_signature()
    body_html = _plain_to_html(body)
    if signature_html:
        body_html = f"<div>{body_html}</div><br><div>{signature_html}</div>"
    else:
        body_html = f"<div>{body_html}</div>"

    html_file = None
    try:
        html_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, prefix="email_draft_",
        )
        html_file.write(body_html)
        html_file.close()

        cmd.extend(["--body-file", html_file.name, "--body-html", body_html])

        logger.debug("Creating draft: to=%s subject=%s", to, subject[:50])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error("Draft creation failed: %s", result.stderr.strip())
            return None

        try:
            data = json.loads(result.stdout)
            draft_id = data.get("id", data.get("draftId", ""))
            logger.info("Draft created: %s", draft_id)
            return draft_id
        except json.JSONDecodeError:
            output = result.stdout.strip()
            if output:
                logger.info("Draft created (raw): %s", output[:100])
                return output
            return None

    except subprocess.TimeoutExpired:
        logger.error("Draft creation timed out")
        return None
    except FileNotFoundError:
        logger.error("gog binary not found at %s", config.GOG_BIN)
        return None
    finally:
        if html_file:
            Path(html_file.name).unlink(missing_ok=True)


def get_draft(draft_id: str) -> Optional[dict]:
    """Fetch a draft by ID. Returns parsed JSON or None."""
    raw = _run_gog("gmail", "drafts", "get", draft_id)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def send_draft(draft_id: str) -> bool:
    """Send a draft by ID. Returns True on success."""
    cmd = [config.GOG_BIN, "gmail", "drafts", "send", draft_id]
    if config.GOG_ACCOUNT:
        cmd.extend(["--account", config.GOG_ACCOUNT])
    cmd.extend(["--json", "--no-input"])

    logger.debug("Sending draft: %s", draft_id)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error("Draft send failed: %s", result.stderr.strip())
            return False
        logger.info("Draft sent: %s", draft_id)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.error("Draft send error: %s", exc)
        return False


def mark_thread_read(thread_id: str) -> bool:
    """Remove the UNREAD label from all messages in a thread."""
    cmd = [
        config.GOG_BIN, "gmail", "thread", "modify", thread_id,
        "--remove", "UNREAD",
    ]
    if config.GOG_ACCOUNT:
        cmd.extend(["--account", config.GOG_ACCOUNT])
    cmd.extend(["--json", "--no-input"])

    logger.debug("Marking thread read: %s", thread_id)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error("Mark-read failed: %s", result.stderr.strip())
            return False
        logger.info("Thread marked read: %s", thread_id)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.error("Mark-read error: %s", exc)
        return False


def draft_reply(
    to: str,
    context: str,
    original_subject: str = "",
    msg_id: Optional[str] = None,
) -> dict:
    """Build and create a draft reply. Returns status dict."""
    subject = original_subject
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    body = context

    draft_id = create_draft(
        to=to,
        subject=subject,
        body=body,
        reply_to_message_id=msg_id,
    )

    if draft_id:
        return {
            "status": "ok",
            "draft_id": draft_id,
            "to": to,
            "subject": subject,
            "body_preview": body[:200],
            "gmail_drafts_url": "https://mail.google.com/mail/u/0/#drafts",
        }
    return {
        "status": "error",
        "error": "Failed to create draft via gog CLI. Check logs for details.",
    }
