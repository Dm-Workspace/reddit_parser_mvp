"""
Google Drive Uploader
Uploads run exports to Google Drive using a Service Account.

ENV:
  GOOGLE_DRIVE_FOLDER_ID               — root folder ID in Drive
  GOOGLE_SERVICE_ACCOUNT_JSON_BASE64   — base64-encoded service account JSON

Folder structure:
  {root_folder}/
    {project_id}/
      {monitor_id}/
        YYYY-MM-DD/
          report.xlsx
          report.json
          handoff.json
"""
import base64
import json
import os
import io
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

# ── MIME types ─────────────────────────────────────────────────────────────────
_MIME = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
    ".csv":  "text/csv",
}
_FOLDER_MIME = "application/vnd.google-apps.folder"

# ── Config ─────────────────────────────────────────────────────────────────────
ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
_SA_B64        = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "")
DRIVE_ENABLED  = bool(ROOT_FOLDER_ID and _SA_B64)


def _get_service():
    """Build and return an authenticated Google Drive v3 service."""
    if not _SA_B64:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is not set")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "google-api-python-client and google-auth are not installed.\n"
            "Run: pip install google-api-python-client google-auth"
        )
    sa_info = json.loads(base64.b64decode(_SA_B64 + "=="))  # pad base64 if needed
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ── Folder helpers ─────────────────────────────────────────────────────────────

def get_or_create_folder(service, parent_id: str, name: str) -> str:
    """Return existing folder ID or create a new one under parent_id."""
    safe_name = name.replace("'", "\\'")
    q = (f"name='{safe_name}' and "
         f"'{parent_id}' in parents and "
         f"mimeType='{_FOLDER_MIME}' and trashed=false")
    results = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": _FOLDER_MIME,
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    logger.debug(f"[Drive] Created folder '{name}' under {parent_id}")
    return folder["id"]


def build_run_folder(project_id: str, monitor_id: str) -> str:
    """
    Ensure folder tree exists: root / project_id / monitor_id / YYYY-MM-DD
    Returns the leaf folder ID.
    """
    if not ROOT_FOLDER_ID:
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID is not set")
    svc = _get_service()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    project_folder  = get_or_create_folder(svc, ROOT_FOLDER_ID, project_id)
    monitor_folder  = get_or_create_folder(svc, project_folder, monitor_id)
    day_folder      = get_or_create_folder(svc, monitor_folder, today)
    return day_folder


# ── Upload ─────────────────────────────────────────────────────────────────────

def upload_file(local_path: str, folder_id: str) -> dict:
    """
    Upload a local file to Google Drive folder.

    Returns:
        {
          "file_id": str,
          "web_view_link": str,
          "download_link": str,
          "file_name": str,
        }
    """
    from googleapiclient.http import MediaFileUpload

    ext = os.path.splitext(local_path)[1].lower()
    mime = _MIME.get(ext, "application/octet-stream")
    file_name = os.path.basename(local_path)

    metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime, resumable=True)

    result = (
        _get_service()
        .files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,webViewLink,webContentLink,name",
        )
        .execute()
    )

    file_id = result["id"]
    web_view = result.get("webViewLink", "")
    # Make file readable by anyone with the link
    _get_service().permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    download_link = f"https://drive.google.com/uc?export=download&id={file_id}"
    logger.info(f"[Drive] Uploaded: {file_name} → {web_view}")
    return {
        "file_id": file_id,
        "web_view_link": web_view,
        "download_link": download_link,
        "file_name": file_name,
    }


def download_file(file_id: str, dest_path: str) -> str:
    """
    Download a file from Google Drive by file_id to dest_path.
    Returns dest_path on success.
    """
    from googleapiclient.http import MediaIoBaseDownload

    svc = _get_service()
    request = svc.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    logger.info(f"[Drive] Downloaded {file_id} → {dest_path}")
    return dest_path


# ── Convenience: upload all exports for a run ──────────────────────────────────

def upload_run_exports(
    export_records,        # List[Export] from storage.models
    project_id: str,
    monitor_id: str,
) -> dict:
    """
    Upload all local export files to Drive.
    Returns mapping: export_id → drive info dict
    """
    if not DRIVE_ENABLED:
        logger.warning("[Drive] Drive not configured — skipping upload")
        return {}

    try:
        folder_id = build_run_folder(project_id, monitor_id)
    except Exception as e:
        logger.error(f"[Drive] Failed to build folder: {e}")
        return {}

    results = {}
    for exp in export_records:
        if not exp.file_path or not os.path.exists(exp.file_path):
            logger.debug(f"[Drive] Skipping {exp.format} — file not found: {exp.file_path}")
            continue
        try:
            info = upload_file(exp.file_path, folder_id)
            results[exp.id] = info
        except Exception as e:
            logger.error(f"[Drive] Upload failed for {exp.file_path}: {e}")

    return results
