"""Central configuration -- reads from .env and exposes typed settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CREDENTIALS_DIR = BASE_DIR / "credentials"
TEMPLATES_DIR = BASE_DIR / "templates"

load_dotenv(BASE_DIR / ".env")

# --- NYS Contract Reporter ---
NYSCR_USERNAME: str = os.getenv("NYSCR_USERNAME", "")
NYSCR_PASSWORD: str = os.getenv("NYSCR_PASSWORD", "")
NYSCR_BASE_URL: str = "https://www.nyscr.ny.gov"

# --- Odoo Cloud CRM ---
ODOO_URL: str = os.getenv("ODOO_URL", "")
ODOO_DB: str = os.getenv("ODOO_DB", "")
ODOO_USER: str = os.getenv("ODOO_USER", "")
ODOO_API_KEY: str = os.getenv("ODOO_API_KEY", "")

# --- Google (shared OAuth2 for Drive, Docs, Gmail) ---
GDRIVE_PARENT_FOLDER_ID: str = os.getenv("GDRIVE_PARENT_FOLDER_ID", "")
GDRIVE_SHARE_EMAIL: str = os.getenv("GDRIVE_SHARE_EMAIL", "")

# --- SQLite ---
RFQS_DB: Path = DATA_DIR / "rfqs.db"

# --- Line cards ---
LINE_CARDS_CSV: Path = DATA_DIR / "line_cards.csv"

# --- Scraper settings ---
RELEVANT_CATEGORIES: list[str] = [
    "Information Technology",
    "Consulting & Other Services",
]

RELEVANCE_KEYWORDS: list[str] = [
    "software",
    "license",
    "saas",
    "subscription",
    "cloud",
    "it services",
    "technology",
    "microsoft",
    "adobe",
    "vmware",
    "citrix",
    "oracle",
    "cisco",
    "dell",
    "hewlett",
    "ibm",
    "sap",
    "salesforce",
    "aws",
    "azure",
    "google cloud",
    "enterprise",
    "renewal",
    "maintenance",
    "support agreement",
]

# Minimum days until due date to consider an RFQ worth pursuing
MIN_DAYS_UNTIL_DUE: int = 7

# Ad types that are NOT competitive solicitations -- skip these entirely
EXCLUDED_AD_TYPES: list[str] = [
    "notice of sole/single source",
    "procurement exempt from advertising",
    "requests for information",
    "requests for comment",
    "grant or notice of funds availability",
    "announcement of surplus property disposal",
    "contractor ads",
]

# --- Notifications ---
TELEGRAM_NOTIFY: bool = os.getenv("TELEGRAM_NOTIFY", "true").lower() == "true"

# --- Company info for proposals ---
COMPANY_NAME: str = "A Aye Aye LLC"
