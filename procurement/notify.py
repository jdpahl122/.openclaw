"""Notification helpers -- sends alerts via Telegram when new RFQs are found."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from data.db import RFQDatabase
from parser.rfq_parser import classify_urgency, filter_and_enrich
from scrapers.nyscr import NYSCRScraper

logger = logging.getLogger(__name__)


def format_rfq_summary(rfqs) -> str:
    """Format a list of RFQs into a readable Telegram message."""
    if not rfqs:
        return ""

    lines = [f"🔔 *{len(rfqs)} New Procurement Opportunity(ies)*\n"]

    for rfq in rfqs:
        urgency = classify_urgency(rfq)
        urgency_icon = {
            "critical": "🔴",
            "urgent": "🟠",
            "normal": "🟡",
            "low": "🟢",
            "unknown": "⚪",
            "expired": "⚫",
        }.get(urgency, "⚪")

        days = rfq.days_until_due
        due_str = f"{rfq.due_date}" if rfq.due_date else "TBD"
        if days is not None:
            due_str += f" ({days}d left)"

        items_str = f" | {len(rfq.line_items)} items" if rfq.line_items else ""

        lines.append(
            f"{urgency_icon} *CR# {rfq.cr_number}*\n"
            f"  {rfq.title[:80]}\n"
            f"  Agency: {rfq.agency}\n"
            f"  Due: {due_str}{items_str}\n"
            f"  Score: {rfq.relevance_score:.2f}\n"
        )

    lines.append(
        "Run `python main.py process` to create Odoo leads and Drive folders."
    )
    return "\n".join(lines)


def run_scan_and_notify() -> None:
    """Scan for new RFQs and output a notification message.

    Designed to be called from OpenClaw cron -- the output is sent
    to the configured Telegram channel by OpenClaw's delivery system.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = RFQDatabase(config.RFQS_DB)
    scraper = NYSCRScraper()

    logger.info("Running scheduled scan...")
    raw_rfqs = scraper.scrape()
    new_rfqs = filter_and_enrich(raw_rfqs, db)

    if new_rfqs:
        message = format_rfq_summary(new_rfqs)
        # Print to stdout -- OpenClaw cron captures this as the response
        print(message)
    else:
        logger.info("No new relevant RFQs found.")
        print("HEARTBEAT_OK")

    db.close()


if __name__ == "__main__":
    run_scan_and_notify()
