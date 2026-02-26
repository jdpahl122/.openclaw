"""Google Drive client -- creates per-RFQ folder structures and uploads files."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Optional

from googleapiclient.http import MediaFileUpload

import config
from integrations.google_auth import get_drive_service
from models.rfq import RFQ

logger = logging.getLogger(__name__)

_SUBFOLDERS = ["Source Documents", "Proposal", "Supporting Docs"]


def create_rfq_folder(rfq: RFQ) -> tuple[str, str]:
    """Create the top-level folder and subfolders for an RFQ.

    Returns:
        (folder_id, folder_url)
    """
    service = get_drive_service()

    # Create top-level folder
    folder_name = rfq.folder_name
    folder_meta = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if config.GDRIVE_PARENT_FOLDER_ID:
        folder_meta["parents"] = [config.GDRIVE_PARENT_FOLDER_ID]

    folder = service.files().create(body=folder_meta, fields="id, webViewLink").execute()
    folder_id = folder["id"]
    folder_url = folder.get("webViewLink", f"https://drive.google.com/drive/folders/{folder_id}")

    logger.info("Created Drive folder: %s (%s)", folder_name, folder_id)

    # Create subfolders
    for sub_name in _SUBFOLDERS:
        sub_meta = {
            "name": sub_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [folder_id],
        }
        sub = service.files().create(body=sub_meta, fields="id").execute()
        logger.debug("Created subfolder: %s (%s)", sub_name, sub["id"])

    return folder_id, folder_url


def get_subfolder_id(
    parent_folder_id: str, subfolder_name: str
) -> Optional[str]:
    """Find a subfolder by name within a parent folder."""
    service = get_drive_service()
    query = (
        f"name = '{subfolder_name}' and "
        f"'{parent_folder_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def upload_file(
    local_path: str,
    parent_folder_id: str,
    filename: Optional[str] = None,
) -> str:
    """Upload a local file to a Drive folder. Returns the file ID."""
    service = get_drive_service()
    p = Path(local_path)
    name = filename or p.name

    mime_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"

    file_meta = {
        "name": name,
        "parents": [parent_folder_id],
    }
    media = MediaFileUpload(local_path, mimetype=mime_type)
    file = (
        service.files()
        .create(body=file_meta, media_body=media, fields="id")
        .execute()
    )
    logger.info("Uploaded %s -> Drive folder %s", name, parent_folder_id)
    return file["id"]


def upload_rfq_attachments(rfq: RFQ) -> int:
    """Upload all RFQ attachments to the 'Source Documents' subfolder.

    Returns the number of files uploaded.
    """
    if not rfq.gdrive_folder_id:
        logger.warning("RFQ %s has no Drive folder -- skip uploads", rfq.cr_number)
        return 0

    source_docs_id = get_subfolder_id(rfq.gdrive_folder_id, "Source Documents")
    if not source_docs_id:
        logger.warning("Source Documents subfolder not found for %s", rfq.cr_number)
        return 0

    uploaded = 0
    for path in rfq.attachment_paths:
        if Path(path).exists():
            try:
                upload_file(path, source_docs_id)
                uploaded += 1
            except Exception as exc:
                logger.warning("Failed to upload %s: %s", path, exc)

    logger.info("Uploaded %d attachments for CR# %s", uploaded, rfq.cr_number)
    return uploaded
