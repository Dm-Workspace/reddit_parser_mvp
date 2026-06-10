from fastapi import APIRouter, Depends
from app.api.deps import get_telegram_user
from storage.models import MAX_ACTIVE_PROJECTS_PER_USER, MAX_ACTIVE_MONITORS_PER_PROJECT

router = APIRouter()

@router.get("/me")
async def get_me(user: dict = Depends(get_telegram_user)):
    return {
        "telegram_id": user["telegram_id"],
        "username": user.get("username", ""),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "limits": {
            "max_projects": MAX_ACTIVE_PROJECTS_PER_USER,
            "max_monitors_per_project": MAX_ACTIVE_MONITORS_PER_PROJECT,
        },
    }
