import re
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.api.deps import get_telegram_user
from storage import database as db
from storage.models import Project, MAX_ACTIVE_PROJECTS_PER_USER

router = APIRouter()


def _make_project_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())[:20].strip("_")
    return f"{slug}_{str(uuid.uuid4())[:6]}"


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    niche: str = ""
    output_language: str = "en"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    niche: Optional[str] = None
    output_language: Optional[str] = None


@router.get("/projects")
async def list_projects(user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    projects = db.list_projects(owner_telegram_id=uid)
    return [_project_dict(p) for p in projects]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    active = db.count_active_projects(uid)
    if active >= MAX_ACTIVE_PROJECTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ACTIVE_PROJECTS_PER_USER} active projects allowed",
        )
    project_id = _make_project_id(body.name)
    project = Project(
        id=project_id,
        owner_telegram_id=uid,
        name=body.name,
        description=body.description,
        niche=body.niche,
        output_language=body.output_language,
        enabled=True,
        archived=False,
    )
    db.create_project(project)
    return _project_dict(project)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_telegram_user)):
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_owner(p.owner_telegram_id, user["telegram_id"])
    return _project_dict(p)


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, user: dict = Depends(get_telegram_user)):
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_owner(p.owner_telegram_id, user["telegram_id"])
    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    if body.niche is not None:
        p.niche = body.niche
    if body.output_language is not None:
        p.output_language = body.output_language
    db.update_project(p)
    return _project_dict(p)


@router.post("/projects/{project_id}/archive")
async def archive_project(project_id: str, user: dict = Depends(get_telegram_user)):
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_owner(p.owner_telegram_id, user["telegram_id"])
    db.archive_project(project_id)
    return {"status": "archived", "project_id": project_id}


def _project_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description or "",
        "niche": p.niche or "",
        "output_language": p.output_language or "en",
        "enabled": p.enabled,
        "archived": p.archived,
        "owner_telegram_id": p.owner_telegram_id,
    }


def _assert_owner(owner_id: int, uid: int):
    if owner_id != 0 and owner_id != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your project")
