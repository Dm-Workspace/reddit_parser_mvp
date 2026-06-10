from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/status")
async def api_status():
    from storage import database as db
    from storage.models import APP_VERSION

    # DB check
    try:
        db.init_db()
        info = db.get_db_info()
        db_status = "connected" if info.get("connected") else "error"
    except Exception as e:
        db_status = f"error: {str(e)[:60]}"

    # Reddit
    try:
        from reddit_client import get_reddit_status
        rs = get_reddit_status()
        reddit_mode = rs.get("effective_mode", "unknown")
    except Exception:
        reddit_mode = "unknown"

    # Drive
    try:
        from drive_uploader import DRIVE_ENABLED
        drive_configured = bool(DRIVE_ENABLED)
    except Exception:
        drive_configured = False

    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "database": db_status,
        "reddit_access_mode": reddit_mode,
        "telegram_bot_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "drive_configured": drive_configured,
        "miniapp_dev_mode": os.environ.get("MINIAPP_DEV_MODE", "false").lower() == "true",
    }
