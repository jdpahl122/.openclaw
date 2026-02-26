"""Excel and CSV parser -- extracts pricing line items from spreadsheets."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Optional

from models.line_item import LineItem

logger = logging.getLogger(__name__)

_HEADER_ALIASES: dict[str, list[str]] = {
    "part_number": ["part", "part no", "part number", "sku", "item no", "item number", "item #", "item"],
    "description": ["description", "desc", "product name", "product", "name", "item description", "line item"],
    "quantity": ["quantity", "qty", "amount", "count", "# of licenses", "no. of licenses"],
    "unit": ["unit", "uom", "unit of measure"],
    "vendor": ["vendor", "manufacturer", "mfg", "mfr", "brand"],
    "unit_price": ["unit price", "price", "cost", "rate", "each", "price per unit"],
    "extended_price": ["extended price", "extended", "total", "ext price", "line total", "total price"],
}


def extract_line_items_from_excel(path: str) -> list[LineItem]:
    """Parse an Excel or CSV file and return extracted line items."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return _parse_csv(path)
    elif p.suffix.lower() in (".xlsx", ".xls"):
        return _parse_xlsx(path)
    else:
        logger.warning("Unsupported spreadsheet format: %s", path)
        return []


def _parse_xlsx(path: str) -> list[LineItem]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.error("openpyxl not installed -- cannot parse Excel: %s", path)
        return []

    items: list[LineItem] = []
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            rows = list(ws.iter_rows(values_only=True))
            items.extend(_parse_rows(rows, source=f"{path}:{sheet}"))
        wb.close()
    except Exception as exc:
        logger.warning("Error parsing Excel %s: %s", path, exc)
    return items


def _parse_csv(path: str) -> list[LineItem]:
    items: list[LineItem] = []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = [tuple(row) for row in reader]
        items.extend(_parse_rows(rows, source=path))
    except Exception as exc:
        logger.warning("Error parsing CSV %s: %s", path, exc)
    return items


def _parse_rows(
    rows: list[tuple], source: str = ""
) -> list[LineItem]:
    """Given raw rows (header + data), detect header and extract items."""
    if len(rows) < 2:
        return []

    # Find the header row (first row with 3+ non-empty cells that match known headers)
    header_idx = _find_header_row(rows)
    if header_idx is None:
        logger.debug("No header row found in %s", source)
        return []

    header = [_normalise(cell) for cell in rows[header_idx]]
    col_map = _map_columns(header)

    if "description" not in col_map:
        logger.debug("No description column found in %s", source)
        return []

    items: list[LineItem] = []
    for row in rows[header_idx + 1 :]:
        item = _row_to_item(row, col_map)
        if item:
            items.append(item)

    logger.info("Extracted %d line items from %s", len(items), source)
    return items


def _find_header_row(rows: list[tuple], max_scan: int = 15) -> Optional[int]:
    """Scan the first N rows to find one that looks like a header."""
    all_aliases = set()
    for aliases in _HEADER_ALIASES.values():
        all_aliases.update(aliases)

    for idx, row in enumerate(rows[:max_scan]):
        if not row:
            continue
        normalised = [_normalise(cell) for cell in row]
        matches = sum(
            1
            for cell in normalised
            if cell and any(alias in cell for alias in all_aliases)
        )
        if matches >= 2:
            return idx
    return None


def _normalise(cell) -> str:
    if cell is None:
        return ""
    return str(cell).strip().lower()


def _map_columns(header: list[str]) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        for idx, h in enumerate(header):
            if any(alias in h for alias in aliases):
                if field not in col_map:
                    col_map[field] = idx
                    break
    return col_map


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^\d.]", "", str(val).strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _row_to_item(
    row: tuple, col_map: dict[str, int]
) -> Optional[LineItem]:

    def _get(field: str) -> str:
        idx = col_map.get(field)
        if idx is None or idx >= len(row):
            return ""
        val = row[idx]
        return str(val).strip() if val is not None else ""

    desc = _get("description")
    if not desc:
        return None

    return LineItem(
        description=desc,
        part_number=_get("part_number"),
        quantity=_safe_float(_get("quantity")),
        unit=_get("unit"),
        vendor=_get("vendor"),
        unit_price=_safe_float(_get("unit_price")),
        extended_price=_safe_float(_get("extended_price")),
    )
