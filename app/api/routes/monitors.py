import json
import re
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.api.deps import get_telegram_user
from storage import database as db
from storage.models import Monitor, MAX_ACTIVE_MONITORS_PER_PROJECT

router = APIRouter()


def _make_monitor_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())[:20].strip("_")
    return f"{slug}_{str(uuid.uuid4())[:6]}"


class MonitorCreate(BaseModel):
    project_id: str
    name: str
    description: str = ""
    source: str = "reddit"
    subreddit_preset_id: Optional[str] = None
    keyword_preset_id: Optional[str] = None
    custom_subreddits: List[str] = []
    custom_keywords: List[str] = []
    run_mode: str = "hot_last_7d"
    schedule_mode: str = "manual"


class MonitorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    run_mode: Optional[str] = None
    schedule_mode: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("/monitors")
async def list_monitors(project_id: Optional[str] = None, user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    monitors = db.list_monitors(project_id=project_id, owner_telegram_id=uid if not project_id else None)
    return [_monitor_dict(m) for m in monitors]


@router.post("/monitors", status_code=status.HTTP_201_CREATED)
async def create_monitor(body: MonitorCreate, user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    project = db.get_project(body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_telegram_id != 0 and project.owner_telegram_id != uid:
        raise HTTPException(status_code=403, detail="Not your project")

    active = db.count_active_monitors(body.project_id)
    if active >= MAX_ACTIVE_MONITORS_PER_PROJECT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_ACTIVE_MONITORS_PER_PROJECT} active monitors per project",
        )

    monitor_id = _make_monitor_id(body.name)
    monitor = Monitor(
        id=monitor_id,
        project_id=body.project_id,
        owner_telegram_id=uid,
        name=body.name,
        description=body.description,
        subreddit_preset_id=body.subreddit_preset_id,
        keyword_preset_id=body.keyword_preset_id,
        custom_subreddits=json.dumps(body.custom_subreddits),
        custom_keywords=json.dumps(body.custom_keywords),
        run_mode=body.run_mode,
        schedule_mode=body.schedule_mode,
        frequency="none",
        schedule_cron="",
        next_run_at=None,
        timezone="UTC",
        min_days_between_runs=7,
        max_runs_per_month=4,
        require_manual_confirmation=True,
        enabled=True,
        archived=False,
    )
    db.create_monitor(monitor)
    return _monitor_dict(monitor)


@router.get("/monitors/{monitor_id}")
async def get_monitor(monitor_id: str, user: dict = Depends(get_telegram_user)):
    m = db.get_monitor(monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
    _assert_owner(m.owner_telegram_id, user["telegram_id"])
    return _monitor_dict(m)


@router.patch("/monitors/{monitor_id}")
async def update_monitor(monitor_id: str, body: MonitorUpdate, user: dict = Depends(get_telegram_user)):
    m = db.get_monitor(monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
    _assert_owner(m.owner_telegram_id, user["telegram_id"])
    if body.name is not None:
        m.name = body.name
    if body.description is not None:
        m.description = body.description
    if body.run_mode is not None:
        m.run_mode = body.run_mode
    if body.schedule_mode is not None:
        m.schedule_mode = body.schedule_mode
    if body.enabled is not None:
        m.enabled = body.enabled
    db.update_monitor(m)
    return _monitor_dict(m)


@router.post("/monitors/{monitor_id}/archive")
async def archive_monitor(monitor_id: str, user: dict = Depends(get_telegram_user)):
    m = db.get_monitor(monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
    _assert_owner(m.owner_telegram_id, user["telegram_id"])
    db.archive_monitor(monitor_id)
    return {"status": "archived", "monitor_id": monitor_id}


@router.post("/monitors/{monitor_id}/run")
async def run_monitor_endpoint(monitor_id: str, user: dict = Depends(get_telegram_user)):
    """Trigger a manual run for this monitor."""
    m = db.get_monitor(monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
    _assert_owner(m.owner_telegram_id, user["telegram_id"])
    if m.archived or not m.enabled:
        raise HTTPException(status_code=400, detail="Monitor is disabled or archived")

    # Check for active run
    active = db.get_active_run_for_monitor(monitor_id)
    if active:
        return {"run_id": active.id, "status": active.status, "message": "Already running"}

    try:
        from app.workers.reddit_worker import RedditWorker
        worker = RedditWorker()
        result = worker.run_monitor_sync(monitor_id)
        return {
            "run_id": result.get("run_id"),
            "status": result.get("status", "completed"),
            "message": result.get("message", ""),
            "total_posts": result.get("total_posts", 0),
            "total_comments": result.get("total_comments", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Run failed: {str(e)[:200]}")


def _monitor_dict(m) -> dict:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "name": m.name,
        "description": m.description or "",
        "run_mode": m.run_mode,
        "schedule_mode": m.schedule_mode,
        "frequency": m.frequency or "none",
        "next_run_at": m.next_run_at,
        "enabled": m.enabled,
        "archived": m.archived,
        "subreddit_preset_id": m.subreddit_preset_id,
        "keyword_preset_id": m.keyword_preset_id,
        "custom_subreddits": _parse_json_list(m.custom_subreddits),
        "custom_keywords": _parse_json_list(m.custom_keywords),
        "last_run_at": getattr(m, "last_run_at", None),
    }


def _parse_json_list(val) -> list:
    if not val:
        return []
    try:
        return json.loads(val)
    except Exception:
        return []


def _assert_owner(owner_id: int, uid: int):
    if owner_id != 0 and owner_id != uid:
        raise HTTPException(status_code=403, detail="Not your monitor")
