"""RFQ data model -- represents a single procurement opportunity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .line_item import LineItem


@dataclass
class RFQ:
    cr_number: str
    title: str
    agency: str
    category: str

    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    ad_end_date: Optional[date] = None

    division: str = ""
    location: str = ""
    ad_type: str = ""
    note: str = ""

    detail_url: str = ""
    source_site: str = "nyscr"

    # Populated by parsers
    raw_text: str = ""
    line_items: list[LineItem] = field(default_factory=list)
    attachment_paths: list[str] = field(default_factory=list)

    # MWBE / SDVOB classification (driven by ad_type)
    procurement_type: str = ""          # e.g. mwbe_sdvob_discretionary, sdvob_set_aside, general
    is_mwbe_sdvob: bool = False         # True when procurement_type is mwbe_sdvob_* or sdvob_set_aside
    sdvob_goal: Optional[float] = None  # supplementary, may be 0% even on MWBE/SDVOB
    mbe_goal: Optional[float] = None
    wbe_goal: Optional[float] = None

    # Set during processing
    relevance_score: float = 0.0
    odoo_lead_id: Optional[int] = None
    gdrive_folder_id: str = ""
    gdrive_folder_url: str = ""

    # Status tracking
    status: str = "new"  # new, processed, quoted, analyzed, proposed
    created_at: Optional[datetime] = None

    @property
    def is_urgent(self) -> bool:
        if not self.due_date:
            return False
        days_left = (self.due_date - date.today()).days
        return days_left <= 7

    @property
    def days_until_due(self) -> Optional[int]:
        if not self.due_date:
            return None
        return (self.due_date - date.today()).days

    @property
    def folder_name(self) -> str:
        short_title = self.title[:60].rstrip()
        return f"{self.cr_number} - {short_title} - {self.agency}"
