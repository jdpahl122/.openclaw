"""Track processed message IDs to avoid duplicate notifications."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class StateStore:
    """Persists processed message IDs and last-check timestamps."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or config.STATE_FILE
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                data.setdefault("drafts", {})
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Corrupted state file, starting fresh: %s", exc)
        return {
            "processed": {},
            "dismissed": [],
            "drafts": {},
            "last_check": None,
            "last_digest": None,
        }

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, default=str))

    def is_processed(self, msg_id: str) -> bool:
        return msg_id in self._data["processed"]

    def mark_processed(self, msg_id: str, category: str, subject: str = "") -> None:
        self._data["processed"][msg_id] = {
            "category": category,
            "subject": subject,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    def dismiss(self, msg_id: str) -> bool:
        """Mark a message as handled/dismissed so it won't resurface."""
        if msg_id not in self._data["dismissed"]:
            self._data["dismissed"].append(msg_id)
            self.save()
            return True
        return False

    def is_dismissed(self, msg_id: str) -> bool:
        return msg_id in self._data["dismissed"]

    def set_last_check(self) -> None:
        self._data["last_check"] = datetime.now(timezone.utc).isoformat()

    def set_last_digest(self, digest: str) -> None:
        self._data["last_digest"] = {
            "text": digest,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_last_digest(self) -> Optional[dict]:
        return self._data.get("last_digest")

    def get_last_check(self) -> Optional[str]:
        return self._data.get("last_check")

    def prune(self, keep_days: int = 7) -> int:
        """Remove entries older than keep_days to prevent unbounded growth."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        before = len(self._data["processed"])

        self._data["processed"] = {
            mid: info for mid, info in self._data["processed"].items()
            if _parse_ts(info.get("processed_at")) > cutoff
        }
        pruned = before - len(self._data["processed"])
        if pruned:
            logger.info("Pruned %d stale state entries", pruned)
        return pruned

    def save_draft(self, draft_id: str, info: dict) -> None:
        self._data["drafts"][draft_id] = {
            **info,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_draft(self, draft_id: str) -> Optional[dict]:
        return self._data["drafts"].get(draft_id)

    def remove_draft(self, draft_id: str) -> None:
        self._data["drafts"].pop(draft_id, None)

    @property
    def draft_count(self) -> int:
        return len(self._data.get("drafts", {}))

    @property
    def processed_count(self) -> int:
        return len(self._data["processed"])


def _parse_ts(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)
