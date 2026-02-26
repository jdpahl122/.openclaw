"""LineItem data model -- a single item extracted from an RFQ pricing sheet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LineItem:
    description: str
    quantity: Optional[float] = None
    unit: str = ""
    part_number: str = ""
    vendor: str = ""
    unit_price: Optional[float] = None
    extended_price: Optional[float] = None
    notes: str = ""

    # Set during line-card matching
    matched_distributors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.matched_distributors is None:
            self.matched_distributors = []

    @property
    def search_text(self) -> str:
        """Combined text used for fuzzy matching against line cards."""
        parts = [self.vendor, self.description, self.part_number]
        return " ".join(p for p in parts if p).lower()
