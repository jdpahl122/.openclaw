"""PDF document parser -- extracts text and tabular data from RFQ PDFs."""

from __future__ import annotations

import logging
import re
from typing import Optional

from models.line_item import LineItem

logger = logging.getLogger(__name__)


def extract_text_from_pdf(path: str) -> tuple[str, list[list[LineItem]]]:
    """Extract full text and any tabular line items from a PDF.

    Returns:
        (full_text, list_of_tables) where each table is a list of LineItem.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed -- cannot parse PDF: %s", path)
        return "", []

    full_text_parts: list[str] = []
    all_tables: list[list[LineItem]] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                text = page.extract_text() or ""
                full_text_parts.append(text)

                # Extract tables
                tables = page.extract_tables() or []
                for table in tables:
                    items = _parse_table(table, page_num)
                    if items:
                        all_tables.append(items)
    except Exception as exc:
        logger.warning("Error parsing PDF %s: %s", path, exc)
        return "", []

    full_text = "\n\n".join(full_text_parts)
    return full_text, all_tables


def _parse_table(
    table: list[list[Optional[str]]], page_num: int
) -> list[LineItem]:
    """Attempt to interpret a PDF table as line items.

    Looks for columns like: part#, description, quantity, unit, price.
    """
    if not table or len(table) < 2:
        return []

    # Try to identify header row
    header_row = table[0]
    if not header_row:
        return []

    headers = [_normalise_header(cell) for cell in header_row]

    # Map logical columns
    col_map = _map_columns(headers)
    if "description" not in col_map:
        # Can't meaningfully parse without at least a description column
        return []

    items: list[LineItem] = []
    for row in table[1:]:
        if not row or all(not cell for cell in row):
            continue
        item = _row_to_line_item(row, col_map)
        if item:
            items.append(item)

    return items


def _normalise_header(cell: Optional[str]) -> str:
    if not cell:
        return ""
    return re.sub(r"[^a-z0-9]", "", cell.lower())


_HEADER_ALIASES: dict[str, list[str]] = {
    "part_number": ["part", "partno", "partnumber", "sku", "itemno", "itemnumber", "item"],
    "description": ["description", "desc", "productname", "product", "name", "itemdescription"],
    "quantity": ["quantity", "qty", "amount", "count", "units"],
    "unit": ["unit", "uom", "unitofmeasure", "measure"],
    "vendor": ["vendor", "manufacturer", "mfg", "mfr", "brand", "make"],
    "unit_price": ["unitprice", "price", "cost", "rate", "each"],
    "extended_price": ["extendedprice", "extended", "total", "extprice", "linetotal", "amount"],
}


def _map_columns(headers: list[str]) -> dict[str, int]:
    """Map logical field names to column indices."""
    col_map: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        for idx, h in enumerate(headers):
            if any(alias in h for alias in aliases):
                if field not in col_map:
                    col_map[field] = idx
                    break
    return col_map


def _safe_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    cleaned = re.sub(r"[^\d.]", "", val.strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _row_to_line_item(
    row: list[Optional[str]], col_map: dict[str, int]
) -> Optional[LineItem]:
    """Convert a table row to a LineItem using the column mapping."""

    def _get(field: str) -> str:
        idx = col_map.get(field)
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

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
