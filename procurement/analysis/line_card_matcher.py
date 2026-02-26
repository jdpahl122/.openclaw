"""Match RFQ line items to distributor line cards for quote requests."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from thefuzz import fuzz

import config
from models.line_item import LineItem

logger = logging.getLogger(__name__)


@dataclass
class DistributorContact:
    distributor_name: str
    rep_name: str
    rep_email: str
    vendor: str
    product_line: str
    notes: str = ""

    @property
    def search_text(self) -> str:
        return f"{self.vendor} {self.product_line}".lower()


@dataclass
class QuoteRequest:
    """A grouped set of line items to send to a single distributor rep."""

    distributor_name: str
    rep_name: str
    rep_email: str
    line_items: list[LineItem]


def load_line_cards(
    csv_path: Optional[Path] = None,
) -> list[DistributorContact]:
    """Load distributor line card entries from CSV."""
    path = csv_path or config.LINE_CARDS_CSV
    if not path.exists():
        logger.warning("Line cards CSV not found: %s", path)
        return []

    contacts: list[DistributorContact] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(
                DistributorContact(
                    distributor_name=row.get("distributor_name", "").strip(),
                    rep_name=row.get("rep_name", "").strip(),
                    rep_email=row.get("rep_email", "").strip(),
                    vendor=row.get("vendor", "").strip(),
                    product_line=row.get("product_line", "").strip(),
                    notes=row.get("notes", "").strip(),
                )
            )

    logger.info("Loaded %d line card entries", len(contacts))
    return contacts


def match_line_items(
    line_items: list[LineItem],
    contacts: list[DistributorContact],
    threshold: int = 55,
) -> list[QuoteRequest]:
    """Match line items to distributors using fuzzy string matching.

    Groups results by distributor rep email so each rep gets one email
    with all matching items.

    Args:
        line_items: Extracted line items from the RFQ.
        contacts: Distributor contacts from line_cards.csv.
        threshold: Minimum fuzz ratio (0-100) to consider a match.

    Returns:
        List of QuoteRequest objects, one per distributor rep.
    """
    if not contacts:
        logger.warning("No line card contacts loaded -- cannot match")
        return []

    # email -> QuoteRequest
    requests_map: dict[str, QuoteRequest] = {}

    for item in line_items:
        item_text = item.search_text
        if not item_text.strip():
            continue

        best_matches: list[tuple[DistributorContact, int]] = []

        for contact in contacts:
            contact_text = contact.search_text
            if not contact_text.strip():
                continue

            # Use token_set_ratio for flexible matching
            score = fuzz.token_set_ratio(item_text, contact_text)
            if score >= threshold:
                best_matches.append((contact, score))

        # Sort by score descending
        best_matches.sort(key=lambda x: x[1], reverse=True)

        if best_matches:
            matched_names: list[str] = []
            for contact, score in best_matches:
                email = contact.rep_email
                if email not in requests_map:
                    requests_map[email] = QuoteRequest(
                        distributor_name=contact.distributor_name,
                        rep_name=contact.rep_name,
                        rep_email=email,
                        line_items=[],
                    )
                # Avoid duplicate items for the same distributor
                if item not in requests_map[email].line_items:
                    requests_map[email].line_items.append(item)
                matched_names.append(contact.distributor_name)

            item.matched_distributors = list(set(matched_names))
            logger.debug(
                "Matched '%s' -> %s (top score: %d)",
                item.description[:40],
                matched_names,
                best_matches[0][1],
            )
        else:
            logger.debug("No match for: %s", item.description[:40])

    results = list(requests_map.values())
    logger.info(
        "Matched %d items across %d distributor quote requests",
        sum(len(qr.line_items) for qr in results),
        len(results),
    )
    return results
