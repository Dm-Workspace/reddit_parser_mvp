"""
Telegram WebApp initData verification.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import os
import urllib.parse
from typing import Optional


MINIAPP_DEV_MODE = os.environ.get("MINIAPP_DEV_MODE", "false").lower() == "true"
MINIAPP_DEV_TELEGRAM_ID = int(os.environ.get("MINIAPP_DEV_TELEGRAM_ID", "0") or "0")


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """
    Validate Telegram WebApp initData and return parsed user dict.
    Raises ValueError on invalid hash.
    Returns: {"telegram_id": int, "username": str, "first_name": str, "last_name": str}
    """
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")

    # Build data_check_string: sorted key=value pairs joined by \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # HMAC-SHA256 with secret_key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid Telegram initData hash")

    user_data = {}
    if "user" in parsed:
        try:
            user_data = json.loads(parsed["user"])
        except (json.JSONDecodeError, KeyError):
            pass

    return {
        "telegram_id": int(user_data.get("id", 0)),
        "username": user_data.get("username", ""),
        "first_name": user_data.get("first_name", ""),
        "last_name": user_data.get("last_name", ""),
    }


def get_current_user(init_data: Optional[str] = None, bot_token: Optional[str] = None) -> dict:
    """
    Returns user dict from initData, or dev-mode fallback.
    """
    if MINIAPP_DEV_MODE:
        return {
            "telegram_id": MINIAPP_DEV_TELEGRAM_ID or 0,
            "username": "dev_user",
            "first_name": "Dev",
            "last_name": "User",
        }

    if not init_data:
        raise ValueError("No initData provided")
    if not bot_token:
        raise ValueError("Bot token not configured")

    return verify_telegram_init_data(init_data, bot_token)
