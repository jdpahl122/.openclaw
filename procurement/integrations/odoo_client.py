"""Odoo Cloud CRM integration via XML-RPC.

Creates leads/opportunities, updates them, and queries historical wins.
"""

from __future__ import annotations

import logging
import xmlrpc.client
from typing import Any, Optional

import config
from models.rfq import RFQ

logger = logging.getLogger(__name__)


class OdooClient:
    """Thin wrapper around Odoo XML-RPC for CRM operations."""

    def __init__(
        self,
        url: str = "",
        db: str = "",
        user: str = "",
        api_key: str = "",
    ) -> None:
        self.url = url or config.ODOO_URL
        self.db = db or config.ODOO_DB
        self.user = user or config.ODOO_USER
        self.api_key = api_key or config.ODOO_API_KEY
        self._uid: Optional[int] = None
        self._models: Optional[xmlrpc.client.ServerProxy] = None

    @property
    def is_configured(self) -> bool:
        """Return True if all required Odoo credentials are present."""
        return bool(self.url and self.db and self.user and self.api_key)

    def _ensure_connection(self) -> None:
        if self._uid is not None:
            return
        if not all([self.url, self.db, self.user, self.api_key]):
            raise RuntimeError(
                "Odoo credentials not configured. "
                "Set ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY in .env"
            )

        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._uid = common.authenticate(self.db, self.user, self.api_key, {})
        if not self._uid:
            raise RuntimeError("Odoo authentication failed -- check credentials")

        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        logger.info("Connected to Odoo: %s (uid=%s)", self.url, self._uid)

    def _execute(self, model: str, method: str, *args, **kwargs) -> Any:
        self._ensure_connection()
        return self._models.execute_kw(  # type: ignore[union-attr]
            self.db, self._uid, self.api_key, model, method, *args, **kwargs
        )

    # --------------------------------------------------------- Tag helpers

    def _ensure_tag(self, tag_name: str) -> int:
        """Find or create a CRM tag by name. Returns the tag ID."""
        ids = self._execute(
            "crm.tag", "search", [[["name", "=", tag_name]]]
        )
        if ids:
            return ids[0]
        new_id = self._execute("crm.tag", "create", [{"name": tag_name}])
        logger.info("Created Odoo CRM tag: %s (id=%s)", tag_name, new_id)
        return new_id

    # --------------------------------------------------- Lead / Opportunity

    def create_lead(self, rfq: RFQ) -> int:
        """Create a CRM lead/opportunity from an RFQ. Returns the lead ID."""
        tag_ids = []
        for tag_name in [
            f"source:{rfq.source_site}",
            f"category:{rfq.category[:50]}",
            f"agency:{rfq.agency[:50]}",
        ]:
            tag_ids.append(self._ensure_tag(tag_name))

        notes_parts = [
            f"CR#: {rfq.cr_number}",
            f"Agency: {rfq.agency}",
            f"Category: {rfq.category}",
            f"Ad Type: {rfq.ad_type}",
            f"Location: {rfq.location}",
            f"Division: {rfq.division}",
            f"Source: {rfq.source_site}",
        ]
        if rfq.detail_url:
            notes_parts.append(f"URL: {rfq.detail_url}")
        if rfq.gdrive_folder_url:
            notes_parts.append(f"Google Drive: {rfq.gdrive_folder_url}")
        if rfq.note:
            notes_parts.append(f"Note: {rfq.note}")

        vals = {
            "name": f"[{rfq.cr_number}] {rfq.title[:120]}",
            "type": "opportunity",
            "description": "\n".join(notes_parts),
            "tag_ids": [(6, 0, tag_ids)],
            "priority": "2" if rfq.is_urgent else "1",
        }

        if rfq.due_date:
            vals["date_deadline"] = rfq.due_date.isoformat()

        lead_id = self._execute("crm.lead", "create", [vals])
        logger.info(
            "Created Odoo opportunity: id=%s for CR# %s", lead_id, rfq.cr_number
        )
        return lead_id

    def update_lead(self, lead_id: int, vals: dict) -> None:
        """Update fields on an existing lead."""
        self._execute("crm.lead", "write", [[lead_id], vals])
        logger.info("Updated Odoo lead %s", lead_id)

    def set_expected_revenue(self, lead_id: int, amount: float) -> None:
        self.update_lead(lead_id, {"expected_revenue": amount})

    # ------------------------------------------------- Historical queries

    def get_won_opportunities(
        self,
        limit: int = 200,
        tag_filter: Optional[str] = None,
    ) -> list[dict]:
        """Fetch historical won opportunities for bid analysis.

        Returns list of dicts with fields: id, name, expected_revenue,
        probability, date_deadline, tag_ids, description.
        """
        domain: list = [["stage_id.is_won", "=", True]]
        if tag_filter:
            tag_ids = self._execute(
                "crm.tag", "search", [[["name", "ilike", tag_filter]]]
            )
            if tag_ids:
                domain.append(["tag_ids", "in", tag_ids])

        fields = [
            "name",
            "expected_revenue",
            "probability",
            "date_deadline",
            "tag_ids",
            "description",
            "date_closed",
        ]
        records = self._execute(
            "crm.lead",
            "search_read",
            [domain],
            {"fields": fields, "limit": limit, "order": "date_closed desc"},
        )
        logger.info("Fetched %d won opportunities from Odoo", len(records))
        return records

    def find_lead_by_cr(self, cr_number: str) -> Optional[int]:
        """Find an existing lead by CR number in the name."""
        ids = self._execute(
            "crm.lead",
            "search",
            [[["name", "ilike", f"[{cr_number}]"]]],
        )
        return ids[0] if ids else None
