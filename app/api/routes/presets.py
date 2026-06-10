import json
import re
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.api.deps import get_telegram_user
from storage import database as db

router = APIRouter()


class SubredditPresetCreate(BaseModel):
    name: str
    subreddits: List[str]


class KeywordPresetCreate(BaseModel):
    name: str
    keywords: List[str]


@router.get("/presets/subreddits")
async def list_subreddit_presets(user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    presets = db.list_subreddit_presets(owner_telegram_id=uid, include_system=True)
    return [_sr_dict(p) for p in presets]


@router.post("/presets/subreddits", status_code=status.HTTP_201_CREATED)
async def create_subreddit_preset(body: SubredditPresetCreate, user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    from storage.models import SubredditPreset
    preset_id = re.sub(r"[^a-z0-9]+", "_", body.name.lower())[:20] + "_" + str(uuid.uuid4())[:6]
    preset = SubredditPreset(
        id=preset_id,
        name=body.name,
        subreddits=json.dumps(body.subreddits),
        owner_telegram_id=uid,
        is_system=False,
    )
    db.create_subreddit_preset(preset)
    return _sr_dict(preset)


@router.get("/presets/keywords")
async def list_keyword_presets(user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    presets = db.list_keyword_presets(owner_telegram_id=uid, include_system=True)
    return [_kw_dict(p) for p in presets]


@router.post("/presets/keywords", status_code=status.HTTP_201_CREATED)
async def create_keyword_preset(body: KeywordPresetCreate, user: dict = Depends(get_telegram_user)):
    uid = user["telegram_id"]
    from storage.models import KeywordPreset
    preset_id = re.sub(r"[^a-z0-9]+", "_", body.name.lower())[:20] + "_" + str(uuid.uuid4())[:6]
    preset = KeywordPreset(
        id=preset_id,
        name=body.name,
        keywords=json.dumps(body.keywords),
        owner_telegram_id=uid,
        is_system=False,
    )
    db.create_keyword_preset(preset)
    return _kw_dict(preset)


def _sr_dict(p) -> dict:
    subs = []
    if p.subreddits:
        try:
            subs = json.loads(p.subreddits)
        except Exception:
            pass
    return {"id": p.id, "name": p.name, "subreddits": subs, "is_system": bool(p.is_system)}


def _kw_dict(p) -> dict:
    kws = []
    if p.keywords:
        try:
            kws = json.loads(p.keywords)
        except Exception:
            pass
    return {"id": p.id, "name": p.name, "keywords": kws, "is_system": bool(p.is_system)}
