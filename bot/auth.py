"""
Authentication helpers for Telegram bot.
Only ADMIN_TELEGRAM_IDS from ENV can use the bot.
"""
import os
from functools import wraps
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes


def get_admin_ids() -> set:
    raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def admin_only(func):
    """Decorator: reject non-admin users."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
        uid = update.effective_user.id
        if uid not in get_admin_ids():
            logger.warning(f"Unauthorized access from user_id={uid}")
            if update.message:
                await update.message.reply_text("⛔ Доступ запрещён.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Доступ запрещён.", show_alert=True)
            return
        # Auto-register user
        try:
            from storage import database as db
            from storage.models import User
            u = update.effective_user
            db.upsert_user(User(
                telegram_id=uid,
                username=u.username or "",
                first_name=u.first_name or "",
                role="admin",
            ))
        except Exception:
            pass
        return await func(update, context)
    return wrapped


def get_uid(obj) -> int:
    """
    Extract Telegram user_id from any of:
      Update, CallbackQuery, Message, User, or None.
    """
    if obj is None:
        return 0
    # telegram.Update — has effective_user
    if hasattr(obj, "effective_user") and obj.effective_user:
        return obj.effective_user.id
    # telegram.CallbackQuery or Message — has from_user
    if hasattr(obj, "from_user") and obj.from_user:
        return obj.from_user.id
    # CallbackQuery.message.from_user fallback
    if hasattr(obj, "message") and obj.message and hasattr(obj.message, "from_user") and obj.message.from_user:
        return obj.message.from_user.id
    # telegram.User — has id directly
    if hasattr(obj, "id") and isinstance(obj.id, int):
        return obj.id
    return 0
