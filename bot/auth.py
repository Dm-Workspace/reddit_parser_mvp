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


def get_uid(update: Update) -> int:
    return update.effective_user.id if update.effective_user else 0
