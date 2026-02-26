"""Google Docs proposal generator -- creates proposal documents in Drive."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import config
from analysis.bid_analyzer import BidSuggestion
from integrations.google_auth import get_docs_service, get_drive_service
from integrations.gdrive_client import get_subfolder_id
from models.rfq import RFQ

logger = logging.getLogger(__name__)


def create_proposal(
    rfq: RFQ,
    bid: Optional[BidSuggestion] = None,
) -> tuple[str, str]:
    """Create a Google Doc proposal in the RFQ's Proposal subfolder.

    Returns:
        (doc_id, doc_url)
    """
    docs_service = get_docs_service()
    drive_service = get_drive_service()

    # Find the Proposal subfolder
    parent_id = None
    if rfq.gdrive_folder_id:
        parent_id = get_subfolder_id(rfq.gdrive_folder_id, "Proposal")

    # Create the document
    doc_title = f"Proposal - {rfq.cr_number} - {rfq.title[:60]}"
    doc_body = {"title": doc_title}
    doc = docs_service.documents().create(body=doc_body).execute()
    doc_id = doc["documentId"]

    # Move to the Proposal subfolder
    if parent_id:
        drive_service.files().update(
            fileId=doc_id,
            addParents=parent_id,
            removeParents="root",
            fields="id, parents",
        ).execute()

    # Build the document content
    requests = _build_doc_requests(rfq, bid)
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    logger.info("Created proposal doc: %s (%s)", doc_title, doc_url)
    return doc_id, doc_url


def _build_doc_requests(
    rfq: RFQ,
    bid: Optional[BidSuggestion],
) -> list[dict]:
    """Build Google Docs API batchUpdate requests to populate the proposal."""
    requests: list[dict] = []
    idx = 1  # Docs API uses 1-based index

    def _insert_text(text: str, bold: bool = False, font_size: int = 11) -> None:
        nonlocal idx
        requests.append(
            {"insertText": {"location": {"index": idx}, "text": text}}
        )
        end = idx + len(text)
        style: dict = {"fontSize": {"magnitude": font_size, "unit": "PT"}}
        if bold:
            style["bold"] = True
        requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": idx, "endIndex": end},
                    "textStyle": style,
                    "fields": "fontSize,bold",
                }
            }
        )
        idx = end

    def _insert_heading(text: str, level: str = "HEADING_1") -> None:
        nonlocal idx
        requests.append(
            {"insertText": {"location": {"index": idx}, "text": text + "\n"}}
        )
        end = idx + len(text) + 1
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": idx, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": level},
                    "fields": "namedStyleType",
                }
            }
        )
        idx = end

    def _insert_line(text: str = "") -> None:
        nonlocal idx
        full = text + "\n"
        requests.append(
            {"insertText": {"location": {"index": idx}, "text": full}}
        )
        idx += len(full)

    # --- Document content ---

    _insert_heading("Technical and Pricing Proposal", "HEADING_1")
    _insert_line()

    _insert_heading(f"Response to: {rfq.title}", "HEADING_2")
    _insert_line(f"CR#: {rfq.cr_number}")
    _insert_line(f"Agency: {rfq.agency}")
    _insert_line(f"Submitted by: {config.COMPANY_NAME}")
    _insert_line(f"Date: {date.today().strftime('%B %d, %Y')}")
    _insert_line()

    # Cover letter
    _insert_heading("1. Cover Letter", "HEADING_2")
    _insert_line(
        f"{config.COMPANY_NAME} is pleased to submit this proposal in response "
        f"to {rfq.title} (CR# {rfq.cr_number}) issued by {rfq.agency}. "
        f"We are committed to delivering high-quality software licensing "
        f"solutions that meet your requirements while providing exceptional value."
    )
    _insert_line()

    # Company overview
    _insert_heading("2. Company Overview", "HEADING_2")
    _insert_line(
        f"{config.COMPANY_NAME} is a technology solutions provider specializing "
        f"in software licensing, subscription services, and IT procurement "
        f"for government agencies."
    )
    _insert_line()

    # Proposed solution
    _insert_heading("3. Proposed Solution", "HEADING_2")
    if rfq.line_items:
        _insert_line("The following items are proposed to fulfill this requirement:")
        _insert_line()
        for i, item in enumerate(rfq.line_items, 1):
            parts = [f"{i}. {item.description}"]
            if item.vendor:
                parts.append(f"  Vendor: {item.vendor}")
            if item.part_number:
                parts.append(f"  Part#: {item.part_number}")
            if item.quantity:
                parts.append(f"  Qty: {item.quantity} {item.unit}")
            _insert_line("  ".join(parts))
    else:
        _insert_line("[Proposed solution details to be added]")
    _insert_line()

    # Pricing
    _insert_heading("4. Pricing", "HEADING_2")
    if bid and bid.mid > 0:
        _insert_line(f"Recommended bid: ${bid.mid:,.2f}")
        _insert_line(f"Bid range: ${bid.low:,.2f} - ${bid.high:,.2f}")
        _insert_line(f"Confidence: {bid.confidence}")
        _insert_line(f"Rationale: {bid.rationale}")
        _insert_line()
    if rfq.line_items:
        for i, item in enumerate(rfq.line_items, 1):
            price_str = f"${item.unit_price:,.2f}" if item.unit_price else "TBD"
            ext_str = f"${item.extended_price:,.2f}" if item.extended_price else "TBD"
            qty_str = str(item.quantity or "TBD")
            _insert_line(
                f"{i}. {item.description[:50]} | Qty: {qty_str} | "
                f"Unit: {price_str} | Extended: {ext_str}"
            )
    else:
        _insert_line("[Pricing table to be completed]")
    _insert_line()

    # Delivery
    _insert_heading("5. Delivery Timeline", "HEADING_2")
    _insert_line(
        "Software licenses will be delivered electronically within 5 business "
        "days of purchase order receipt, subject to vendor processing times."
    )
    _insert_line()

    # Terms
    _insert_heading("6. Terms and Conditions", "HEADING_2")
    _insert_line("- All prices are valid for 90 days from the date of this proposal.")
    _insert_line("- Licensing terms are subject to the manufacturer's standard EULA.")
    _insert_line("- Payment terms: Net 30 upon delivery and acceptance.")
    _insert_line()

    # MWBE / SDVOB compliance (if applicable)
    if rfq.is_mwbe_sdvob or rfq.sdvob_goal or rfq.mbe_goal or rfq.wbe_goal:
        _insert_heading("7. MWBE / SDVOB Compliance", "HEADING_2")
        if rfq.is_mwbe_sdvob:
            ptype_label = rfq.procurement_type.replace("_", " ").title()
            _insert_line(f"Procurement Type: {ptype_label}")
        goals_parts = []
        if rfq.sdvob_goal is not None:
            goals_parts.append(f"SDVOB Goal: {rfq.sdvob_goal}%")
        if rfq.mbe_goal is not None:
            goals_parts.append(f"MBE Goal: {rfq.mbe_goal}%")
        if rfq.wbe_goal is not None:
            goals_parts.append(f"WBE Goal: {rfq.wbe_goal}%")
        if goals_parts:
            _insert_line(" | ".join(goals_parts))
        _insert_line(
            f"{config.COMPANY_NAME} is committed to meeting all MWBE and SDVOB "
            f"participation goals set forth in this solicitation."
        )
        _insert_line()

        # Past performance
        _insert_heading("8. Past Performance", "HEADING_2")
        _insert_line("[Past performance references to be added]")
        _insert_line()

        # Contact
        _insert_heading("9. Contact Information", "HEADING_2")
    else:
        # Past performance
        _insert_heading("7. Past Performance", "HEADING_2")
        _insert_line("[Past performance references to be added]")
        _insert_line()

        # Contact
        _insert_heading("8. Contact Information", "HEADING_2")
    _insert_line(config.COMPANY_NAME)

    return requests
