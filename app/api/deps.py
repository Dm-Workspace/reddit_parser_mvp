"""
FastAPI dependency injection helpers.
"""
import os
from fastapi import Header, HTTPException, status
from app.api.auth import get_current_user, MINIAPP_DEV_MODE

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def get_telegram_user(x_telegram_init_data: str = Header(default="")) -> dict:
    """
    Dependency: extract and validate Telegram user from request header.
    Header: X-Telegram-Init-Data
    """
    if not x_telegram_init_data and not MINIAPP_DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Telegram-Init-Data header required",
        )
    try:
        return get_current_user(init_data=x_telegram_init_data or None, bot_token=BOT_TOKEN)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
