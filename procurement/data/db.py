"""SQLite database for tracking RFQs and their processing status."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from models.rfq import RFQ
from models.line_item import LineItem


def _adapt_date(val: date) -> str:
    return val.isoformat()


def _convert_date(val: bytes) -> date:
    return date.fromisoformat(val.decode())


def _adapt_datetime(val: datetime) -> str:
    return val.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    return datetime.fromisoformat(val.decode())


sqlite3.register_adapter(date, _adapt_date)
sqlite3.register_converter("DATE", _convert_date)
sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("TIMESTAMP", _convert_datetime)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS rfqs (
    cr_number       TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    agency          TEXT NOT NULL,
    category        TEXT NOT NULL,
    issue_date      DATE,
    due_date        DATE,
    ad_end_date     DATE,
    division        TEXT DEFAULT '',
    location        TEXT DEFAULT '',
    ad_type         TEXT DEFAULT '',
    note            TEXT DEFAULT '',
    detail_url      TEXT DEFAULT '',
    source_site     TEXT DEFAULT 'nyscr',
    raw_text        TEXT DEFAULT '',
    line_items_json TEXT DEFAULT '[]',
    attachment_paths_json TEXT DEFAULT '[]',
    procurement_type TEXT DEFAULT '',
    is_mwbe_sdvob   INTEGER DEFAULT 0,
    sdvob_goal      REAL,
    mbe_goal        REAL,
    wbe_goal        REAL,
    relevance_score REAL DEFAULT 0.0,
    odoo_lead_id    INTEGER,
    gdrive_folder_id TEXT DEFAULT '',
    gdrive_folder_url TEXT DEFAULT '',
    status          TEXT DEFAULT 'new',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class RFQDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(db_path), detect_types=sqlite3.PARSE_DECLTYPES
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns that may be missing from older databases."""
        cur = self._conn.execute("PRAGMA table_info(rfqs)")
        existing = {row["name"] for row in cur.fetchall()}
        migrations = [
            ("procurement_type", "TEXT DEFAULT ''"),
            ("is_mwbe_sdvob", "INTEGER DEFAULT 0"),
            ("sdvob_goal", "REAL"),
            ("mbe_goal", "REAL"),
            ("wbe_goal", "REAL"),
        ]
        for col, typedef in migrations:
            if col not in existing:
                self._conn.execute(f"ALTER TABLE rfqs ADD COLUMN {col} {typedef}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- helpers --

    def _row_to_rfq(self, row: sqlite3.Row) -> RFQ:
        d = dict(row)
        items_raw = json.loads(d.pop("line_items_json", "[]"))
        attachments = json.loads(d.pop("attachment_paths_json", "[]"))
        line_items = [LineItem(**li) for li in items_raw]
        # SQLite stores booleans as integers
        if "is_mwbe_sdvob" in d:
            d["is_mwbe_sdvob"] = bool(d["is_mwbe_sdvob"])
        return RFQ(
            **{k: v for k, v in d.items() if k in RFQ.__dataclass_fields__},
            line_items=line_items,
            attachment_paths=attachments,
        )

    def _rfq_to_params(self, rfq: RFQ) -> dict:
        items_json = json.dumps(
            [
                {
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit": li.unit,
                    "part_number": li.part_number,
                    "vendor": li.vendor,
                    "unit_price": li.unit_price,
                    "extended_price": li.extended_price,
                    "notes": li.notes,
                }
                for li in rfq.line_items
            ]
        )
        return {
            "cr_number": rfq.cr_number,
            "title": rfq.title,
            "agency": rfq.agency,
            "category": rfq.category,
            "issue_date": rfq.issue_date,
            "due_date": rfq.due_date,
            "ad_end_date": rfq.ad_end_date,
            "division": rfq.division,
            "location": rfq.location,
            "ad_type": rfq.ad_type,
            "note": rfq.note,
            "detail_url": rfq.detail_url,
            "source_site": rfq.source_site,
            "raw_text": rfq.raw_text,
            "line_items_json": items_json,
            "attachment_paths_json": json.dumps(rfq.attachment_paths),
            "procurement_type": rfq.procurement_type,
            "is_mwbe_sdvob": int(rfq.is_mwbe_sdvob),
            "sdvob_goal": rfq.sdvob_goal,
            "mbe_goal": rfq.mbe_goal,
            "wbe_goal": rfq.wbe_goal,
            "relevance_score": rfq.relevance_score,
            "odoo_lead_id": rfq.odoo_lead_id,
            "gdrive_folder_id": rfq.gdrive_folder_id,
            "gdrive_folder_url": rfq.gdrive_folder_url,
            "status": rfq.status,
            "created_at": rfq.created_at or datetime.now(),
        }

    # -- CRUD --

    def exists(self, cr_number: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM rfqs WHERE cr_number = ?", (cr_number,)
        )
        return cur.fetchone() is not None

    def upsert(self, rfq: RFQ) -> None:
        params = self._rfq_to_params(rfq)
        cols = ", ".join(params.keys())
        placeholders = ", ".join(f":{k}" for k in params.keys())
        updates = ", ".join(
            f"{k} = :{k}" for k in params.keys() if k != "cr_number"
        )
        sql = f"""
            INSERT INTO rfqs ({cols}) VALUES ({placeholders})
            ON CONFLICT(cr_number) DO UPDATE SET {updates}
        """
        self._conn.execute(sql, params)
        self._conn.commit()

    def get(self, cr_number: str) -> Optional[RFQ]:
        cur = self._conn.execute(
            "SELECT * FROM rfqs WHERE cr_number = ?", (cr_number,)
        )
        row = cur.fetchone()
        return self._row_to_rfq(row) if row else None

    def get_by_status(self, status: str) -> list[RFQ]:
        cur = self._conn.execute(
            "SELECT * FROM rfqs WHERE status = ? ORDER BY due_date ASC",
            (status,),
        )
        return [self._row_to_rfq(r) for r in cur.fetchall()]

    def get_all(self) -> list[RFQ]:
        cur = self._conn.execute("SELECT * FROM rfqs ORDER BY due_date ASC")
        return [self._row_to_rfq(r) for r in cur.fetchall()]

    def update_status(self, cr_number: str, status: str) -> None:
        self._conn.execute(
            "UPDATE rfqs SET status = ? WHERE cr_number = ?",
            (status, cr_number),
        )
        self._conn.commit()

    def update_field(self, cr_number: str, field: str, value) -> None:
        allowed = set(RFQ.__dataclass_fields__.keys()) | {
            "line_items_json",
            "attachment_paths_json",
        }
        if field not in allowed:
            raise ValueError(f"Unknown field: {field}")
        self._conn.execute(
            f"UPDATE rfqs SET {field} = ? WHERE cr_number = ?",
            (value, cr_number),
        )
        self._conn.commit()
