#!/Users/jpahl/.pyenv/versions/3.11.11/bin/python3
"""OpenClaw skill query interface for the email monitor.

This script is called by the OpenClaw agent via the exec tool.
All output goes to stdout as text for the agent to relay.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from classifier import classify
from drafter import draft_reply, get_draft, mark_thread_read, send_draft
from formatter import format_digest
from scanner import fetch_message, fetch_unread
from state import StateStore


@click.group()
def cli():
    """Email monitor query interface for OpenClaw agent."""
    pass


@cli.command()
@click.option("--max-results", default=25)
@click.option("--query", default="")
def check(max_results: int, query: str):
    """Check inbox and print digest."""
    store = StateStore()
    messages = fetch_unread(max_results=max_results, query=query)

    if not messages:
        print("No unread messages in inbox.")
        return

    new_messages = [
        m for m in messages
        if not store.is_processed(m.msg_id) and not store.is_dismissed(m.msg_id)
    ]

    if not new_messages:
        print(f"All {len(messages)} unread messages already processed. No new emails.")
        return

    classified = [(msg, classify(msg)) for msg in new_messages]

    for msg, cls in classified:
        store.mark_processed(msg.msg_id, cls.category, msg.subject)

    store.set_last_check()

    digest = format_digest(classified)
    if digest:
        print(digest)
        store.set_last_digest(digest)

    store.prune()
    store.save()


@cli.command()
def last():
    """Show the last generated digest."""
    store = StateStore()
    last_digest = store.get_last_digest()
    if last_digest:
        print(last_digest["text"])
        print(f"\n(Generated: {last_digest['generated_at']})")
    else:
        print("No previous digest found. Run 'check' first.")


@cli.command()
@click.option("--msg-id", required=True, help="Gmail message ID")
def show(msg_id: str):
    """Fetch and display a single email."""
    msg = fetch_message(msg_id)
    if not msg:
        print(f"Could not fetch message {msg_id}")
        return

    print(f"From: {msg.sender} <{msg.sender_email}>")
    print(f"To: {msg.to}")
    print(f"Subject: {msg.subject}")
    print(f"Date: {msg.date}")
    print(f"URL: {msg.gmail_url}")
    if msg.has_attachments:
        print("Attachments: Yes")
    print(f"\n{msg.body_plain[:3000]}")


@cli.command()
@click.option("--to", "to_addr", required=True, help="Recipient email address")
@click.option("--context", required=True, help="What to say in the reply")
@click.option("--subject", default="", help="Email subject (optional)")
@click.option("--msg-id", default=None, help="Original message ID for threading")
@click.option("--thread-id", default=None, help="Thread ID (for mark-read on send)")
def draft(to_addr: str, context: str, subject: str, msg_id: str, thread_id: str):
    """Draft a reply email."""
    result = draft_reply(
        to=to_addr,
        context=context,
        original_subject=subject,
        msg_id=msg_id,
    )

    if result["status"] == "ok":
        store = StateStore()
        store.save_draft(result["draft_id"], {
            "to": result["to"],
            "subject": result["subject"],
            "msg_id": msg_id or "",
            "thread_id": thread_id or "",
            "body_preview": result["body_preview"],
        })
        store.save()

        print(f"Draft created successfully!")
        print(f"Draft ID: {result['draft_id']}")
        print(f"To: {result['to']}")
        print(f"Subject: {result['subject']}")
        print(f"Preview: {result['body_preview']}")
        print(f"\nView drafts: {result['gmail_drafts_url']}")
        print(f"\nTo review: query.py show-draft --draft-id {result['draft_id']}")
        print(f"To send:   query.py send --draft-id {result['draft_id']}")
    else:
        print(f"Error: {result['error']}")


@cli.command("show-draft")
@click.option("--draft-id", required=True, help="Draft ID to display")
def show_draft(draft_id: str):
    """Fetch and display a draft email for review."""
    import base64
    import re
    from html.parser import HTMLParser

    data = get_draft(draft_id)
    if not data:
        print(f"Could not fetch draft {draft_id}")
        return

    draft_obj = data.get("draft", data)
    msg = draft_obj.get("message", {})
    headers = {}
    for h in msg.get("payload", {}).get("headers", []):
        headers[h.get("name", "").lower()] = h.get("value", "")

    print(f"From: {headers.get('from', '(unknown)')}")
    print(f"To: {headers.get('to', '(unknown)')}")
    print(f"Subject: {headers.get('subject', '(no subject)')}")
    print(f"Date: {headers.get('date', '(not set)')}")
    print()

    body_raw = ""
    body_data = msg.get("payload", {}).get("body", {}).get("data", "")
    if body_data:
        try:
            body_raw = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        except Exception:
            body_raw = ""

    if not body_raw:
        body_raw = msg.get("snippet", "") or "(empty body)"

    if "<" in body_raw and ">" in body_raw:
        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._parts: list[str] = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag == "br":
                    self._parts.append("\n")
                if tag in ("div", "p", "tr", "li"):
                    if self._parts and not self._parts[-1].endswith("\n"):
                        self._parts.append("\n")
                if tag in ("style", "script"):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ("style", "script"):
                    self._skip = False
                if tag in ("div", "p", "tr"):
                    self._parts.append("\n")
            def handle_data(self, d):
                if not self._skip:
                    self._parts.append(d)
            def get_text(self) -> str:
                return "".join(self._parts)

        extractor = _TextExtractor()
        try:
            extractor.feed(body_raw)
            body = extractor.get_text()
        except Exception:
            body = body_raw
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
    else:
        body = body_raw

    print(body[:3000])
    print(f"\nDraft ID: {draft_id}")
    print(f"To send this draft: query.py send --draft-id {draft_id}")


@cli.command("send")
@click.option("--draft-id", required=True, help="Draft ID to send")
def send(draft_id: str):
    """Send a draft and mark the original thread as read."""
    store = StateStore()
    draft_info = store.get_draft(draft_id)

    ok = send_draft(draft_id)
    if not ok:
        print(f"Failed to send draft {draft_id}. Check logs.")
        return

    print(f"Draft sent successfully!")

    thread_id = draft_info.get("thread_id", "") if draft_info else ""
    if thread_id:
        read_ok = mark_thread_read(thread_id)
        if read_ok:
            print(f"Thread {thread_id} marked as read.")
        else:
            print(f"Warning: could not mark thread {thread_id} as read.")
    else:
        msg_id = draft_info.get("msg_id", "") if draft_info else ""
        if msg_id:
            read_ok = mark_thread_read(msg_id)
            if read_ok:
                print(f"Original message thread marked as read.")
            else:
                print(f"Warning: could not mark original message as read.")

    if draft_info:
        store.remove_draft(draft_id)
        store.save()
        print(f"\nSent to: {draft_info.get('to', '(unknown)')}")
        print(f"Subject: {draft_info.get('subject', '(unknown)')}")


@cli.command()
@click.option("--msg-id", required=True, help="Message ID to dismiss")
def dismiss(msg_id: str):
    """Mark a message as handled so it won't appear in future digests."""
    store = StateStore()
    if store.dismiss(msg_id):
        print(f"Message {msg_id} dismissed.")
    else:
        print(f"Message {msg_id} was already dismissed.")


@cli.command()
def status():
    """Show monitor status."""
    store = StateStore()
    info = {
        "last_check": store.get_last_check() or "never",
        "processed_count": store.processed_count,
        "pending_drafts": store.draft_count,
        "gog_account": config.GOG_ACCOUNT or "(not set)",
    }
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    cli()
