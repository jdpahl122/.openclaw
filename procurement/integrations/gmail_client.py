"""Gmail API client -- creates draft quote request emails."""

from __future__ import annotations

import base64
import logging
from datetime import date, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import config
from analysis.line_card_matcher import QuoteRequest
from integrations.google_auth import get_gmail_service
from models.rfq import RFQ

logger = logging.getLogger(__name__)


def _format_line_items_table(items) -> str:
    """Format line items as a readable plain-text table for the email body."""
    if not items:
        return "(No specific line items extracted -- see attached RFQ documents)"

    lines = []
    lines.append(f"{'#':<4} {'Part/SKU':<20} {'Description':<45} {'Qty':<8} {'Unit':<8}")
    lines.append("-" * 90)

    for idx, item in enumerate(items, 1):
        part = (item.part_number or "N/A")[:18]
        desc = (item.description or "")[:43]
        qty = str(item.quantity or "TBD")[:6]
        unit = (item.unit or "ea")[:6]
        lines.append(f"{idx:<4} {part:<20} {desc:<45} {qty:<8} {unit:<8}")

    return "\n".join(lines)


def _compose_email(
    rfq: RFQ,
    quote_request: QuoteRequest,
    template_path: Optional[Path] = None,
) -> MIMEText:
    """Compose a quote request email from template."""
    tpl_path = template_path or config.TEMPLATES_DIR / "quote_request.txt"
    template = tpl_path.read_text(encoding="utf-8")

    # Quote deadline = RFQ due date minus 5 days (or 3 days from now, whichever is later)
    if rfq.due_date:
        quote_deadline = rfq.due_date - timedelta(days=5)
        if quote_deadline < date.today() + timedelta(days=3):
            quote_deadline = date.today() + timedelta(days=3)
        deadline_str = quote_deadline.strftime("%B %d, %Y")
    else:
        deadline_str = "ASAP"

    due_date_str = rfq.due_date.strftime("%B %d, %Y") if rfq.due_date else "TBD"

    body = template.format(
        rep_name=quote_request.rep_name,
        distributor_name=quote_request.distributor_name,
        rfq_title=rfq.title,
        cr_number=rfq.cr_number,
        agency=rfq.agency,
        due_date=due_date_str,
        quote_deadline=deadline_str,
        line_items_table=_format_line_items_table(quote_request.line_items),
    )

    subject = f"Quote Request - {rfq.title[:60]} - CR# {rfq.cr_number} - Due {due_date_str}"

    msg = MIMEText(body)
    msg["to"] = quote_request.rep_email
    msg["subject"] = subject

    return msg


def create_draft_quote_requests(
    rfq: RFQ,
    quote_requests: list[QuoteRequest],
) -> list[dict]:
    """Create Gmail drafts for each distributor quote request.

    Returns a list of draft metadata dicts (id, message link).
    """
    if not quote_requests:
        logger.info("No quote requests to create for CR# %s", rfq.cr_number)
        return []

    service = get_gmail_service()
    drafts_created: list[dict] = []

    for qr in quote_requests:
        msg = _compose_email(rfq, qr)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        try:
            draft = (
                service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute()
            )
            draft_id = draft.get("id", "")
            logger.info(
                "Created Gmail draft for %s (%s) -- draft ID: %s",
                qr.rep_name,
                qr.distributor_name,
                draft_id,
            )
            drafts_created.append(
                {
                    "draft_id": draft_id,
                    "distributor": qr.distributor_name,
                    "rep_name": qr.rep_name,
                    "rep_email": qr.rep_email,
                    "item_count": len(qr.line_items),
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to create draft for %s: %s", qr.rep_email, exc
            )

    logger.info(
        "Created %d Gmail drafts for CR# %s", len(drafts_created), rfq.cr_number
    )
    return drafts_created
