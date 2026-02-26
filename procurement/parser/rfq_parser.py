"""RFQ relevance filter, deduplication, and urgency classification."""

from __future__ import annotations

import logging
from datetime import date

import config
from data.db import RFQDatabase
from models.rfq import RFQ
from parser.doc_parser import extract_text_from_pdf
from parser.excel_parser import extract_line_items_from_excel

logger = logging.getLogger(__name__)


def classify_procurement_type(ad_type: str) -> tuple[str, bool]:
    """Classify an RFQ's procurement type from the raw ad_type string.

    Returns (procurement_type, is_mwbe_sdvob).
    The ad_type field is the authoritative source -- goal percentages may be 0%
    even on MWBE/SDVOB procurements.
    """
    lower = ad_type.lower()
    if "mwbe" in lower and "sdvob" in lower and "discretionary" in lower:
        return "mwbe_sdvob_discretionary", True
    if "sdvob" in lower and "set" in lower and "aside" in lower:
        return "sdvob_set_aside", True
    if "sdvob" in lower and "discretionary" in lower:
        return "sdvob_discretionary", True
    if "mwbe" in lower and "discretionary" in lower:
        return "mwbe_discretionary", True
    if "discretionary" in lower:
        return "discretionary", False
    if "continuous" in lower:
        return "continuous", False
    return "general", False


# Score boost applied to MWBE/SDVOB procurement types
_MWBE_SDVOB_BOOST = 0.10


def is_competitive_solicitation(rfq: RFQ) -> bool:
    """Return False for sole-source notices, RFIs, grants, and other
    non-competitive ad types that aren't actual solicitations for quotes."""
    ad_type_lower = rfq.ad_type.lower()
    for excluded in config.EXCLUDED_AD_TYPES:
        if excluded in ad_type_lower:
            return False
    return True


def compute_relevance(rfq: RFQ) -> float:
    """Score an RFQ 0-1 based on keyword matches in title, category, and text."""
    searchable = " ".join(
        [
            rfq.title,
            rfq.category,
            rfq.agency,
            rfq.raw_text[:5000],
            rfq.note,
        ]
    ).lower()

    hits = sum(1 for kw in config.RELEVANCE_KEYWORDS if kw in searchable)
    max_possible = len(config.RELEVANCE_KEYWORDS)
    return min(hits / max(max_possible * 0.15, 1), 1.0)


def is_relevant(rfq: RFQ, threshold: float = 0.90) -> bool:
    """Return True if the RFQ is likely about software/licensing."""
    return rfq.relevance_score >= threshold


def classify_urgency(rfq: RFQ) -> str:
    """Return urgency label based on due date proximity."""
    if rfq.due_date is None:
        return "unknown"
    days = (rfq.due_date - date.today()).days
    if days < 0:
        return "expired"
    if days <= 3:
        return "critical"
    if days <= 7:
        return "urgent"
    if days <= 14:
        return "normal"
    return "low"


def process_attachments(rfq: RFQ) -> RFQ:
    """Parse PDF and Excel attachments, enrich the RFQ with extracted content."""
    extra_text_parts: list[str] = []
    for path in rfq.attachment_paths:
        lower = path.lower()
        if lower.endswith(".pdf"):
            text, tables = extract_text_from_pdf(path)
            extra_text_parts.append(text)
            # Tables from PDFs can contain line items
            for table in tables:
                rfq.line_items.extend(table)
        elif lower.endswith((".xlsx", ".xls", ".csv")):
            items = extract_line_items_from_excel(path)
            rfq.line_items.extend(items)

    if extra_text_parts:
        rfq.raw_text = rfq.raw_text + "\n\n--- ATTACHMENTS ---\n\n" + "\n\n".join(
            extra_text_parts
        )
    return rfq


def filter_and_enrich(
    rfqs: list[RFQ],
    db: RFQDatabase,
    threshold: float = 0.90,
) -> list[RFQ]:
    """Full parsing pipeline: dedup, filter ad type, classify, parse, score.

    Returns only new, relevant, competitive-solicitation RFQs.  All RFQs
    (including irrelevant ones) are stored in the DB for dedup tracking.
    """
    new_rfqs: list[RFQ] = []

    for rfq in rfqs:
        # Dedup
        if db.exists(rfq.cr_number):
            logger.debug("Skipping duplicate CR# %s", rfq.cr_number)
            continue

        # Classify procurement type from ad_type (before any filtering)
        rfq.procurement_type, rfq.is_mwbe_sdvob = classify_procurement_type(
            rfq.ad_type
        )

        # Skip non-competitive ad types (sole source, RFI, grants, etc.)
        if not is_competitive_solicitation(rfq):
            logger.info(
                "Skipping non-competitive CR# %s | %s | ad_type=%s",
                rfq.cr_number,
                rfq.title[:50],
                rfq.ad_type[:60],
            )
            db.upsert(rfq)  # still track for dedup
            continue

        # Skip RFQs due too soon (or already past)
        if rfq.due_date is not None:
            days_left = (rfq.due_date - date.today()).days
            if days_left < config.MIN_DAYS_UNTIL_DUE:
                logger.info(
                    "Skipping CR# %s | %s | due in %d days (need >= %d)",
                    rfq.cr_number,
                    rfq.title[:50],
                    days_left,
                    config.MIN_DAYS_UNTIL_DUE,
                )
                db.upsert(rfq)
                continue

        # Parse attachments
        rfq = process_attachments(rfq)

        # Score relevance
        rfq.relevance_score = compute_relevance(rfq)

        # Boost MWBE/SDVOB opportunities
        if rfq.is_mwbe_sdvob:
            rfq.relevance_score = min(rfq.relevance_score + _MWBE_SDVOB_BOOST, 1.0)

        # Persist regardless of relevance (for dedup tracking)
        db.upsert(rfq)

        mwbe_tag = " [MWBE/SDVOB]" if rfq.is_mwbe_sdvob else ""
        if is_relevant(rfq, threshold):
            urgency = classify_urgency(rfq)
            logger.info(
                "Relevant RFQ: CR# %s | %s | score=%.2f | urgency=%s%s",
                rfq.cr_number,
                rfq.title[:50],
                rfq.relevance_score,
                urgency,
                mwbe_tag,
            )
            new_rfqs.append(rfq)
        else:
            logger.info(
                "Below threshold: CR# %s | %s | score=%.2f (need >= %.2f)%s",
                rfq.cr_number,
                rfq.title[:50],
                rfq.relevance_score,
                threshold,
                mwbe_tag,
            )

    logger.info(
        "Filter result: %d relevant out of %d total RFQs "
        "(threshold=%.2f, excluded non-competitive)",
        len(new_rfqs), len(rfqs), threshold,
    )
    return new_rfqs
