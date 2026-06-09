#!/usr/bin/env python3
"""
Telegram Bot — Trend Intelligence Hub
Entry point: wires all handlers and starts polling.

ENV:
  TELEGRAM_BOT_TOKEN  — from @BotFather
  ADMIN_TELEGRAM_IDS  — comma-separated Telegram user IDs
"""
import os
import sys

# ── Load .env FIRST — before any os.environ reads or module imports ───────────
try:
    from dotenv import load_dotenv
    _dotenv_loaded = load_dotenv()
except ImportError:
    _dotenv_loaded = False   # Railway injects ENV directly — dotenv not required


from loguru import logger
from utils.logger import setup_logger

try:
    from telegram import Update
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        MessageHandler, filters,
    )
except ImportError:
    print("python-telegram-bot not installed. Run: pip install python-telegram-bot")
    sys.exit(1)


def main():
    setup_logger("INFO")

    # Read token AFTER load_dotenv() so local .env is picked up
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    # ── Startup diagnostics (no secrets printed) ──────────────────────────────
    logger.debug(f".env loaded         : {'yes' if _dotenv_loaded else 'no (Railway/system ENV used)'}")
    logger.info (f"TELEGRAM_BOT_TOKEN  : {'SET' if BOT_TOKEN else 'NOT SET'}")
    logger.info (f"ADMIN_TELEGRAM_IDS  : {'SET' if os.environ.get('ADMIN_TELEGRAM_IDS') else 'NOT SET'}")
    logger.debug(f"REDDIT_ACCESS_MODE  : {os.environ.get('REDDIT_ACCESS_MODE', 'playwright (default)')}")

    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set — add it to .env or Railway ENV variables")
        sys.exit(1)

    # ── Init DB + seed system presets ──────────────────────────────────────────
    try:
        from storage import database as db
        db.init_db()
        from config_loader import seed_system_presets, sync_monitors_yaml
        seed_system_presets()
        sync_monitors_yaml()   # optional: load monitors.yaml if it exists
    except Exception as e:
        logger.error(f"Startup init failed: {e}")

    # ── Build Telegram Application ────────────────────────────────────────────
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Conversation handlers (must be first — they intercept text messages) ──
    from bot.project_flow import build_create_project_handler
    from bot.monitor_flow import build_create_monitor_handler
    app.add_handler(build_create_project_handler())
    app.add_handler(build_create_monitor_handler())

    # ── Simple commands ────────────────────────────────────────────────────────
    from bot.commands import (
        cmd_start, cmd_menu, cmd_projects, cmd_monitors, cmd_run,
        cmd_schedule, cmd_next_runs, cmd_runs, cmd_latest,
        cmd_download, cmd_drive, cmd_presets, cmd_status,
        handle_unknown,
    )
    app.add_handler(CommandHandler("start",             cmd_start))
    app.add_handler(CommandHandler("menu",              cmd_menu))
    app.add_handler(CommandHandler("projects",          cmd_projects))
    app.add_handler(CommandHandler("monitors",          cmd_monitors))
    app.add_handler(CommandHandler("run",               cmd_run))
    app.add_handler(CommandHandler("schedule",          cmd_schedule))
    app.add_handler(CommandHandler("schedule_manual",   _schedule_quick("manual")))
    app.add_handler(CommandHandler("schedule_weekly",   _schedule_quick("weekly")))
    app.add_handler(CommandHandler("schedule_biweekly", _schedule_quick("biweekly")))
    app.add_handler(CommandHandler("schedule_monthly",  _schedule_quick("monthly")))
    app.add_handler(CommandHandler("schedule_disable",  _schedule_quick("disabled")))
    app.add_handler(CommandHandler("next_runs",         cmd_next_runs))
    app.add_handler(CommandHandler("runs",              cmd_runs))
    app.add_handler(CommandHandler("latest",            cmd_latest))
    app.add_handler(CommandHandler("download",          cmd_download))
    app.add_handler(CommandHandler("drive",             cmd_drive))
    app.add_handler(CommandHandler("presets",           cmd_presets))
    app.add_handler(CommandHandler("status",            cmd_status))

    # ── Archive commands ───────────────────────────────────────────────────────
    app.add_handler(CommandHandler("archive_project", _cmd_archive("project")))
    app.add_handler(CommandHandler("archive_monitor", _cmd_archive("monitor")))

    # ── Callback handlers ──────────────────────────────────────────────────────
    from bot.commands import (
        handle_menu_callback, handle_proj_callback, handle_mon_callback,
        handle_run_callbacks, handle_archive_confirm, handle_schedule_callback,
        handle_schedule_day_cb, cancel_action,
    )
    app.add_handler(CallbackQueryHandler(handle_menu_callback,    pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(handle_proj_callback,    pattern=r"^proj:"))
    app.add_handler(CallbackQueryHandler(handle_mon_callback,     pattern=r"^mon:"))
    app.add_handler(CallbackQueryHandler(handle_run_callbacks,    pattern=r"^run_(start|force):"))
    app.add_handler(CallbackQueryHandler(handle_archive_confirm,  pattern=r"^confirm_archive:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_callback,pattern=r"^sch:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_day_cb,  pattern=r"^(sch_day|sch_dom):"))
    app.add_handler(CallbackQueryHandler(cancel_action,           pattern=r"^cancel_action$"))

    # ── Fallback: unknown text/commands ────────────────────────────────────────
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown))

    # ── Global error handler ──────────────────────────────────────────────────
    async def error_handler(upd, ctx):
        logger.exception(f"Unhandled Telegram error: {ctx.error}", exc_info=ctx.error)
        try:
            if upd and upd.effective_message:
                await upd.effective_message.reply_text(
                    "⚠️ Произошла ошибка. Вернитесь в меню: /menu"
                )
        except Exception:
            pass

    app.add_error_handler(error_handler)

    logger.info("🤖 Telegram bot started. Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# ── Quick schedule helpers ─────────────────────────────────────────────────────

def _schedule_quick(mode: str):
    """
    Factory for /schedule_manual, /schedule_biweekly, /schedule_disable.
    For weekly/monthly — requires extra args (weekday/day HH:MM).
    """
    from bot.auth import admin_only as _ao
    from bot.schedule_utils import compute_next_run_at

    @_ao
    async def handler(update, context):
        if not context.args:
            await update.message.reply_text(f"Использование: /schedule_{mode} <monitor_id> [день] [HH:MM]")
            return
        monitor_id = context.args[0]
        from storage import database as db
        monitor = db.get_monitor(monitor_id)
        if not monitor:
            await update.message.reply_text(f"❌ Монитор {monitor_id} не найден.")
            return

        from bot.schedule_utils import frequency_label, build_weekly_cron, build_monthly_cron, parse_time

        if mode in ("manual", "disabled"):
            monitor.schedule_mode = mode if mode == "disabled" else "manual"
            monitor.frequency     = "none" if mode in ("manual", "disabled") else monitor.frequency
            monitor.schedule_cron = ""
            monitor.next_run_at   = None
        elif mode == "biweekly":
            monitor.schedule_mode = "scheduled"
            monitor.frequency     = "biweekly"
            monitor.schedule_cron = ""
            monitor.next_run_at   = compute_next_run_at("biweekly", "", monitor.timezone)
        elif mode in ("weekly", "monthly"):
            if len(context.args) < 3:
                await update.message.reply_text(
                    f"Для {mode} укажите: /schedule_{mode} <monitor_id> <день> <HH:MM>\n"
                    f"Пример weekly: /schedule_weekly wellness_hot 1 08:00  (1=Пн)\n"
                    f"Пример monthly: /schedule_monthly wellness_hot 1 08:00  (1=1-е число)"
                )
                return
            try:
                day         = int(context.args[1])
                hour, minute = parse_time(context.args[2])
            except (ValueError, IndexError) as e:
                await update.message.reply_text(f"❌ {e}")
                return
            if mode == "weekly":
                cron = build_weekly_cron(day % 7, hour, minute)
            else:
                cron = build_monthly_cron(max(1, min(28, day)), hour, minute)
            monitor.schedule_mode = "scheduled"
            monitor.frequency     = mode
            monitor.schedule_cron = cron
            monitor.next_run_at   = compute_next_run_at(mode, cron, monitor.timezone)

        db.update_monitor(monitor)
        sched = frequency_label(monitor.frequency, monitor.schedule_cron)
        next_str = (monitor.next_run_at or "—")[:16]
        await update.message.reply_text(
            f"✅ Расписание обновлено!\n\n"
            f"📡 <b>{monitor.name}</b>\n"
            f"🕒 {sched}\n"
            f"📅 Следующий запуск: {next_str}",
            parse_mode="HTML",
        )
    handler.__name__ = f"schedule_{mode}"
    return handler


def _cmd_archive(entity: str):
    """Factory for /archive_project and /archive_monitor."""
    from bot.auth import admin_only as _ao
    from storage import database as db

    @_ao
    async def handler(update, context):
        if not context.args:
            await update.message.reply_text(f"Использование: /archive_{entity} <id>")
            return
        eid = context.args[0]
        if entity == "project":
            db.archive_project(eid)
        else:
            db.archive_monitor(eid)
        await update.message.reply_text(
            f"🗄 {entity.capitalize()} <code>{eid}</code> архивирован.",
            parse_mode="HTML",
        )
    handler.__name__ = f"archive_{entity}"
    return handler


if __name__ == "__main__":
    main()
