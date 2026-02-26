"""Shared Google OAuth2 authentication for Drive, Docs, and Gmail.

Uses the OAuth client credentials JSON file and a single cached token
that covers all required scopes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_ALL_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.compose",
]

_CLIENT_SECRETS_FILE = config.CREDENTIALS_DIR / "google-oauth-client.json"
_TOKEN_FILE = config.CREDENTIALS_DIR / "google-token.json"

# Also check legacy filename from initial setup
_LEGACY_SECRETS_FILE = config.CREDENTIALS_DIR / "gdrive-service-account.json"


def _find_client_secrets() -> Path:
    """Locate the OAuth client secrets JSON file."""
    if _CLIENT_SECRETS_FILE.exists():
        return _CLIENT_SECRETS_FILE
    if _LEGACY_SECRETS_FILE.exists():
        return _LEGACY_SECRETS_FILE
    raise RuntimeError(
        f"Google OAuth client secrets file not found.\n"
        f"Expected at: {_CLIENT_SECRETS_FILE}\n"
        f"Download it from Google Cloud Console > APIs & Services > Credentials > OAuth 2.0 Client IDs"
    )


def get_google_creds():
    """Build or refresh OAuth2 credentials covering Drive, Docs, and Gmail.

    On first run, opens a browser for interactive consent.  The refresh
    token is cached to disk for all subsequent runs.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(_TOKEN_FILE), _ALL_SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google OAuth token...")
            creds.refresh(Request())
        else:
            secrets_file = _find_client_secrets()
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets_file), _ALL_SCOPES
            )
            # Try browser-based flow first, fall back to console
            try:
                logger.info(
                    "Starting Google OAuth consent flow (browser will open)..."
                )
                creds = flow.run_local_server(
                    port=8085,
                    open_browser=True,
                    timeout_seconds=120,
                )
            except Exception as exc:
                logger.warning("Browser flow failed (%s), trying console flow...", exc)
                auth_url, _ = flow.authorization_url(prompt="consent")
                print(f"\nOpen this URL in your browser to authorize:\n\n{auth_url}\n")
                code = input("Paste the authorization code here: ").strip()
                flow.fetch_token(code=code)
                creds = flow.credentials

        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json())
        logger.info("Google OAuth token saved to %s", _TOKEN_FILE)

    return creds


def get_drive_service():
    """Return an authenticated Google Drive v3 service."""
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=get_google_creds())


def get_docs_service():
    """Return an authenticated Google Docs v1 service."""
    from googleapiclient.discovery import build
    return build("docs", "v1", credentials=get_google_creds())


def get_gmail_service():
    """Return an authenticated Gmail v1 service."""
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=get_google_creds())
