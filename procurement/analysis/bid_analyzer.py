"""Bid analyzer -- uses historical Odoo wins to suggest pricing for new RFQs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from integrations.odoo_client import OdooClient
from models.rfq import RFQ

logger = logging.getLogger(__name__)


@dataclass
class BidSuggestion:
    """Pricing recommendation for an RFQ."""

    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    confidence: str = "low"  # low, medium, high
    rationale: str = ""
    comparable_deals: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"Suggested bid range: ${self.low:,.2f} - ${self.high:,.2f} "
            f"(recommended: ${self.mid:,.2f}) | "
            f"Confidence: {self.confidence} | "
            f"Based on {len(self.comparable_deals)} comparable deal(s)"
        )


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text for similarity matching."""
    stop = {
        "the", "a", "an", "and", "or", "for", "of", "to", "in", "on",
        "with", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can",
        "nys", "new", "york", "state", "services", "department",
    }
    words = set(re.findall(r"\b[a-z]{3,}\b", text.lower()))
    return words - stop


def _similarity(kw_a: set[str], kw_b: set[str]) -> float:
    """Jaccard similarity between two keyword sets."""
    if not kw_a or not kw_b:
        return 0.0
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    return len(intersection) / len(union)


def analyze_bid(
    rfq: RFQ,
    odoo: Optional[OdooClient] = None,
    margin_pct: float = 0.15,
) -> BidSuggestion:
    """Generate a bid suggestion for an RFQ based on historical data.

    Steps:
    1. Pull won opportunities from Odoo.
    2. Find deals with similar keywords (title, category, agency).
    3. Compute price statistics from comparable deals.
    4. Apply margin and confidence scoring.
    """
    if odoo is None:
        logger.info("No Odoo client provided -- using fallback pricing")
        return _fallback_suggestion(rfq)

    # Fetch historical wins
    try:
        won = odoo.get_won_opportunities(limit=300)
    except Exception as exc:
        logger.warning("Could not fetch Odoo history: %s", exc)
        return _fallback_suggestion(rfq)

    if not won:
        logger.info("No historical wins -- using fallback pricing")
        return _fallback_suggestion(rfq)

    # Build keyword set for the current RFQ
    rfq_keywords = _extract_keywords(
        f"{rfq.title} {rfq.category} {rfq.agency} {rfq.raw_text[:2000]}"
    )

    # Score similarity against historical deals
    comparable: list[tuple[dict, float]] = []
    for deal in won:
        deal_text = f"{deal.get('name', '')} {deal.get('description', '')}"
        deal_keywords = _extract_keywords(deal_text)
        sim = _similarity(rfq_keywords, deal_keywords)
        revenue = deal.get("expected_revenue") or 0
        if sim > 0.1 and revenue > 0:
            comparable.append((deal, sim))

    comparable.sort(key=lambda x: x[1], reverse=True)
    top_comparable = comparable[:10]

    if not top_comparable:
        logger.info("No comparable deals found -- using fallback")
        return _fallback_suggestion(rfq)

    # Compute price statistics
    revenues = [deal.get("expected_revenue", 0) for deal, _ in top_comparable]
    revenues = [r for r in revenues if r > 0]

    if not revenues:
        return _fallback_suggestion(rfq)

    avg_revenue = sum(revenues) / len(revenues)
    min_revenue = min(revenues)
    max_revenue = max(revenues)

    # Determine confidence based on number and quality of comparables
    avg_sim = sum(sim for _, sim in top_comparable) / len(top_comparable)
    if len(top_comparable) >= 5 and avg_sim > 0.25:
        confidence = "high"
    elif len(top_comparable) >= 3 and avg_sim > 0.15:
        confidence = "medium"
    else:
        confidence = "low"

    # Apply margin
    low = min_revenue * (1 + margin_pct * 0.5)
    mid = avg_revenue * (1 + margin_pct)
    high = max_revenue * (1 + margin_pct * 1.5)

    # If we have line items with unit prices, use them as a cost basis
    total_cost = sum(
        (li.unit_price or 0) * (li.quantity or 1) for li in rfq.line_items
    )
    if total_cost > 0:
        cost_based_mid = total_cost * (1 + margin_pct)
        mid = (mid + cost_based_mid) / 2

    comparable_details = [
        {
            "name": deal.get("name", ""),
            "revenue": deal.get("expected_revenue", 0),
            "similarity": round(sim, 2),
        }
        for deal, sim in top_comparable[:5]
    ]

    rationale_parts = [
        f"Based on {len(top_comparable)} comparable won deal(s).",
        f"Average historical revenue: ${avg_revenue:,.2f}.",
        f"Average similarity score: {avg_sim:.2f}.",
    ]
    if total_cost > 0:
        rationale_parts.append(
            f"RFQ line-item cost basis: ${total_cost:,.2f} "
            f"(with {margin_pct*100:.0f}% margin: ${total_cost * (1 + margin_pct):,.2f})."
        )

    return BidSuggestion(
        low=round(low, 2),
        mid=round(mid, 2),
        high=round(high, 2),
        confidence=confidence,
        rationale=" ".join(rationale_parts),
        comparable_deals=comparable_details,
    )


def _fallback_suggestion(rfq: RFQ) -> BidSuggestion:
    """Generate a rough estimate when no historical data is available."""
    total_cost = sum(
        (li.unit_price or 0) * (li.quantity or 1) for li in rfq.line_items
    )

    if total_cost > 0:
        low = total_cost * 1.08
        mid = total_cost * 1.15
        high = total_cost * 1.25
        rationale = (
            f"No comparable historical deals. "
            f"Estimate based on line-item costs (${total_cost:,.2f}) "
            f"with 8-25% margin."
        )
    else:
        low = 0.0
        mid = 0.0
        high = 0.0
        rationale = (
            "No comparable historical deals and no line-item pricing available. "
            "Manual pricing required."
        )

    return BidSuggestion(
        low=round(low, 2),
        mid=round(mid, 2),
        high=round(high, 2),
        confidence="low",
        rationale=rationale,
    )
