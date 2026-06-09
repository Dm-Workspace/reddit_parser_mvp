"""
Google Drive Uploader — service account based.

ENV:
  GOOGLE_DRIVE_FOLDER_ID               — root folder ID in Drive
  GOOGLE_SERVICE_ACCOUNT_JSON_BASE64   — base64-encoded service account JSON

Folder structure:
  {root_folder}/
    {owner_telegram_id}/
      {project_id}/
        {monitor_id}/
          YYYY-MM-DD/
            {run_id}.xlsx
            {run_id}.json
            {run_id}_handoff.json

Drive failure policy:
  - Drive upload failure does NOT fail the run
  - Run gets status=completed_with_warning instead
  - Local file is kept when Drive upload fails
  - Local file is deleted only after successful upload (if CLEANUP_LOCAL_FILES=true)
"""
import base64
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from loguru import logger

_MIME = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
    ".csv":  "text/csv",
}
_FOLDER_MIME = "application/vnd.google-apps.folder"

ROOT_FOLDER_ID  = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
_SA_B64         = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "")
DRIVE_ENABLED   = bool(ROOT_FOLDER_ID and _SA_B64)
CLEANUP_LOCAL   = os.environ.get("CLEANUP_LOCAL_FILES", "false").lower() == "true"


def _get_service():
    if not _SA_B64:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is not set")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Run: pip install google-api-python-client google-auth"
        )
    padded  = _SA_B64 + "=" * (-len(_SA_B64) % 4)
    sa_info = json.loads(base64.b64decode(padded))
    creds   = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ── Folder helpers ─────────────────────────────────────────────────────────────

def get_or_create_folder(service, parent_id: str, name: str) -> str:
    safe = name.replace("'", "\\'")
    q    = (
        f"name='{safe}' and '{parent_id}' in parents and "
        f"mimeType='{_FOLDER_MIME}' and trashed=false"
    )
    res   = service.files().list(q=q, fields="files(id)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta   = {"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]}
    folder = service.files().create(body=meta, fields="id").execute()
    logger.debug(f"[Drive] Folder created: {name}")
    return folder["id"]


def build_run_folder(owner_telegram_id, project_id: str, monitor_id: str) -> str:
    """
    Ensure path: root / {owner_id} / {project_id} / {monitor_id} / YYYY-MM-DD
    Returns leaf folder ID.
    """
    if not ROOT_FOLDER_ID:
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID is not set")
    svc   = _get_service()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    owner_folder   = get_or_create_folder(svc, ROOT_FOLDER_ID, str(owner_telegram_id))
    project_folder = get_or_create_folder(svc, owner_folder,   project_id)
    monitor_folder = get_or_create_folder(svc, project_folder, monitor_id)
    day_folder     = get_or_create_folder(svc, monitor_folder, today)
    return day_folder


# ── Upload / Download ──────────────────────────────────────────────────────────

def upload_file(local_path: str, folder_id: str) -> dict:
    """Upload a file. Returns dict with file_id, web_view_link, download_link, file_size."""
    from googleapiclient.http import MediaFileUpload
    ext   = os.path.splitext(local_path)[1].lower()
    mime  = _MIME.get(ext, "application/octet-stream")
    fname = os.path.basename(local_path)
    meta  = {"name": fname, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
    svc   = _get_service()
    res   = svc.files().create(
        body=meta, media_body=media, fields="id,webViewLink,name,size"
    ).execute()
    fid   = res["id"]
    svc.permissions().create(
        fileId=fid, body={"type": "anyone", "role": "reader"}
    ).execute()
    web_view      = res.get("webViewLink", "")
    download_link = f"https://drive.google.com/uc?export=download&id={fid}"
    file_size     = int(res.get("size", 0) or 0) or _local_size(local_path)
    logger.info(f"[Drive] {fname} → {web_view}")
    return {
        "file_id":       fid,
        "web_view_link": web_view,
        "download_link": download_link,
        "file_size":     file_size,
    }


def _local_size(path: str) -> Optional[int]:
    try:
        return os.path.getsize(path)
    except Exception:
        return None


def download_file(file_id: str, dest_path: str) -> str:
    from googleapiclient.http import MediaIoBaseDownload
    svc = _get_service()
    req = svc.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
    return dest_path


# ── Bulk upload for a run ──────────────────────────────────────────────────────

def upload_run_exports(
    export_records,
    owner_telegram_id,
    project_id: str,
    monitor_id: str,
) -> Tuple[Dict[str, dict], bool]:
    """
    Upload all local export files to Drive.

    Returns:
        (results, had_errors)
        results: mapping export_id → drive info dict
        had_errors: True if at least one upload failed (caller can set warning)

    Never raises — Drive failure is non-fatal.
    """
    if not DRIVE_ENABLED:
        logger.debug("[Drive] Not configured — skipping upload")
        return {}, False

    try:
        folder_id = build_run_folder(owner_telegram_id, project_id, monitor_id)
    except Exception as e:
        logger.error(f"[Drive] Folder creation failed: {e}")
        return {}, True   # had_errors=True

    results: Dict[str, dict] = {}
    had_errors = False

    for exp in export_records:
        if not exp.file_path or not os.path.exists(exp.file_path):
            logger.debug(f"[Drive] Skip (no local file): {getattr(exp, 'file_name', exp.id)}")
            continue
        try:
            info = upload_file(exp.file_path, folder_id)
            results[exp.id] = info
            # Delete local file only after confirmed upload
            if CLEANUP_LOCAL:
                try:
                    os.remove(exp.file_path)
                    logger.debug(f"[Drive] Local file removed: {exp.file_path}")
                except Exception as rm_err:
                    logger.warning(f"[Drive] Could not remove local file: {rm_err}")
        except Exception as e:
            logger.error(f"[Drive] Upload failed for {exp.file_path}: {e}")
            had_errors = True
            # Keep local file on failure

    return results, had_errors
