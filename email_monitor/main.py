#!/Users/jpahl/.pyenv/versions/3.11.11/bin/python3
"""Gmail Email Monitor -- CLI entrypoint (cron-friendly).

Fetches unread emails, classifies them, and prints a digest to stdout.
OpenClaw cron delivers stdout to Telegram.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from classifier import classify
from formatter import format_digest
from scanner import fetch_unread
from state import StateStore

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("email_monitor")


@click.group()
def cli():
    """Gmail Email Monitor for OpenClaw."""
    pass


@cli.command()
@click.option("--max-results", default=25, help="Max unread messages to fetch")
@click.option("--query", default="", help="Additional Gmail search query")
@click.option("--json-output", is_flag=True, help="Output JSON instead of digest")
def check(max_results: int, query: str, json_output: bool):
    """Fetch unread emails, classify, and print digest."""
    store = StateStore()

    messages = fetch_unread(max_results=max_results, query=query)
    if not messages:
        logger.info("No unread messages found")
        return

    new_messages = [
        m for m in messages
        if not store.is_processed(m.msg_id) and not store.is_dismissed(m.msg_id)
    ]

    if not new_messages:
        logger.info("All %d unread messages already processed", len(messages))
        return

    classified = [(msg, classify(msg)) for msg in new_messages]

    for msg, cls in classified:
        store.mark_processed(msg.msg_id, cls.category, msg.subject)

    store.set_last_check()

    if json_output:
        output = {
            "total": len(classified),
            "emails": [
                {
                    "msg_id": msg.msg_id,
                    "subject": msg.subject,
                    "sender": msg.sender_email,
                    "category": cls.category,
                    "score": round(cls.score, 2),
                    "url": msg.gmail_url,
                    "date": msg.date.isoformat() if msg.date else None,
                }
                for msg, cls in classified
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        digest = format_digest(classified)
        if digest:
            print(digest)
            store.set_last_digest(digest)

    store.prune()
    store.save()


@cli.command()
def status():
    """Show last check time and state summary."""
    store = StateStore()
    info = {
        "last_check": store.get_last_check() or "never",
        "processed_count": store.processed_count,
        "state_file": str(config.STATE_FILE),
        "gog_account": config.GOG_ACCOUNT or "(not set)",
    }
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    cli()
