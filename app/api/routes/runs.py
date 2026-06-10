import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from app.api.deps import get_telegram_user
from storage import database as db

router = APIRouter()


@router.get("/runs")
async def list_runs(
    project_id: Optional[str] = None,
    monitor_id: Optional[str] = None,
    limit: int = 20,
    user: dict = Depends(get_telegram_user),
):
    runs = db.list_runs(limit=limit, project_id=project_id, monitor_id=monitor_id)
    return [_run_dict(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_telegram_user)):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    exports = db.list_exports_for_run(run_id)
    d = _run_dict(run)
    d["exports"] = [_export_dict(e) for e in exports]
    return d


@router.get("/runs/{run_id}/download/{fmt}")
async def download_run_file(run_id: str, fmt: str, user: dict = Depends(get_telegram_user)):
    """fmt: xlsx | json | handoff"""
    if fmt not in ("xlsx", "json", "handoff"):
        raise HTTPException(status_code=400, detail="Invalid format. Use: xlsx, json, handoff")

    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    exports = db.list_exports_for_run(run_id)
    # map "handoff" → "handoff_json"
    lookup_fmt = "handoff_json" if fmt == "handoff" else fmt
    export = next((e for e in exports if e.format == lookup_fmt), None)

    if not export:
        raise HTTPException(status_code=404, detail=f"No {fmt} export for this run")

    # Local file
    if export.file_path and os.path.exists(export.file_path):
        media_types = {
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "handoff": "application/json",
        }
        filename = os.path.basename(export.file_path)
        return FileResponse(export.file_path, media_type=media_types[fmt], filename=filename)

    # Google Drive link
    if export.drive_web_view_link:
        return JSONResponse({"drive_url": export.drive_web_view_link})

    raise HTTPException(status_code=404, detail="File not available locally or in Drive")


def _run_dict(r) -> dict:
    return {
        "id": r.id,
        "monitor_id": r.monitor_id,
        "project_id": r.project_id,
        "status": r.status,
        "total_posts": r.total_posts or 0,
        "total_comments": r.total_comments or 0,
        "quality_status": r.quality_status or "",
        "warning_message": r.warning_message or "",
        "error_message": r.error_message or "",
        "started_at": r.started_at or "",
        "finished_at": getattr(r, "finished_at", None) or "",
        "export_path": r.export_path or "",
    }


def _export_dict(e) -> dict:
    return {
        "id": e.id,
        "format": e.format,
        "file_path": e.file_path or "",
        "drive_file_id": getattr(e, "drive_file_id", "") or "",
        "drive_web_view_link": getattr(e, "drive_web_view_link", "") or "",
    }
