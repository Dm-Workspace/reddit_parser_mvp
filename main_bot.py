#!/usr/bin/env python3
"""
Telegram Bot — Multi-Monitor Trend Intelligence System

Commands:
  /start                  welcome message
  /projects               list projects
  /monitors               list monitors with last run status
  /run <monitor_id>       queue a monitor run
  /latest                 latest run per monitor
  /runs [limit]           recent run history
  /download <run_id>      send Excel file in chat
  /drive <run_id>         show Google Drive links
  /status                 system status

Access: restricted to ADMIN_TELEGRAM_IDS (comma-separated in ENV)

ENV:
  TELEGRAM_BOT_TOKEN     — from @BotFather
  ADMIN_TELEGRAM_IDS     — e.g. "123456789,987654321"
"""
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from loguru import logger

try:
    from telegram import Update, constants
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, MessageHandler, filters
    )
except ImportError:
    print("python-telegram-bot not installed. Run: pip install python-telegram-bot")
    sys.exit(1)

from utils.logger import setup_logger

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_ADMIN_IDS_RAW = os.environ.get("ADMIN_TELEGRAM_IDS", "")


def _get_admin_ids() -> set:
    ids = set()
    for part in _ADMIN_IDS_RAW.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


# ── Auth decorator ─────────────────────────────────────────────────────────────

def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
        if update.effective_user.id not in _get_admin_ids():
            await update.message.reply_text("⛔ Access denied.")
            logger.warning(f"Unauthorized access: user_id={update.effective_user.id}")
            return
        return await func(update, context)
    return wrapped


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _status_icon(status: str) -> str:
    return {
        "queued":               "📋",
        "running":              "⚙️",
        "completed":            "✅",
        "completed_with_warning": "⚠️",
        "failed":               "❌",
    }.get(status, "❓")


def _quality_icon(quality: str) -> str:
    return "✅" if quality == "ok" else "⚠️"


def _format_run(run) -> str:
    icon = _status_icon(run.status)
    q    = _quality_icon(run.quality_status or "ok")
    started = (run.started_at or "")[:16]
    return (
        f"{icon} <code>{run.id}</code> | <b>{run.monitor_id}</b>\n"
        f"   {q} {run.quality_status or 'ok'} | "
        f"{run.total_posts} posts, {run.total_comments} comments\n"
        f"   🕐 {started}\n"
    )


def _format_run_result(run, exports) -> str:
    """Format the full run completion message for bot notification."""
    icon = _status_icon(run.status)
    lines = [
        f"{icon} <b>Run {run.status.upper()}</b>",
        f"",
        f"🏷 <b>Project:</b> {run.project_id}",
        f"📡 <b>Monitor:</b> {run.monitor_id}",
        f"🆔 <b>Run ID:</b> <code>{run.id}</code>",
        f"",
        f"📊 <b>Posts:</b> {run.total_posts}",
        f"💬 <b>Comments:</b> {run.total_comments}",
        f"🔬 <b>Quality:</b> {_quality_icon(run.quality_status or 'ok')} {run.quality_status or 'ok'}",
    ]
    if run.warning_message:
        lines.append(f"⚠️ {run.warning_message}")

    # Top keywords
    if run.top_keywords_json:
        try:
            kws = json.loads(run.top_keywords_json)
            kw_str = ", ".join(f"{k['keyword']} ({k['total_mentions']})" for k in kws[:6])
            lines += ["", f"🔑 <b>Top keywords:</b>", f"   {kw_str}"]
        except Exception:
            pass

    # Drive links
    drive_lines = []
    fmt_icons = {"xlsx": "📊", "json": "📄", "handoff_json": "🤖", "csv_posts": "📋", "csv_comments": "📋"}
    for exp in exports:
        if exp.drive_web_view_link:
            ico = fmt_icons.get(exp.format, "📁")
            label = exp.format.upper().replace("_", " ")
            drive_lines.append(f"   {ico} <a href='{exp.drive_web_view_link}'>{label}</a>")
    if drive_lines:
        lines += ["", "☁️ <b>Google Drive:</b>"] + drive_lines
    elif run.export_path:
        lines += ["", f"📁 <b>Local export:</b> <code>{run.export_path}</code>"]

    if run.status == "failed" and run.error_message:
        lines += ["", f"💥 <b>Error:</b> <code>{run.error_message[:200]}</code>"]

    return "\n".join(lines)


# ── Background run ─────────────────────────────────────────────────────────────

async def _run_in_background(bot, chat_id: int, monitor_id: str, run_id: str):
    """Execute run in thread pool and notify when done."""
    from monitor_runner import run_monitor
    from storage import database as db

    try:
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(
            None, lambda: run_monitor(monitor_id, existing_run_id=run_id)
        )
        if run:
            exports = db.list_exports_for_run(run.id)
            msg = _format_run_result(run, exports)
        else:
            msg = f"❌ Run failed to start for <code>{monitor_id}</code>"
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML",
                               disable_web_page_preview=True)
    except Exception as e:
        logger.exception(f"Background run failed: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Run crashed: <code>{str(e)[:300]}</code>",
            parse_mode="HTML",
        )


# ── Command handlers ───────────────────────────────────────────────────────────

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Trend Intelligence Hub</b>\n\n"
        "Commands:\n"
        "/projects — projects\n"
        "/monitors — monitors & status\n"
        "/run &lt;monitor_id&gt; — run a monitor\n"
        "/latest — latest run per monitor\n"
        "/runs — recent history\n"
        "/download &lt;run_id&gt; — get Excel\n"
        "/drive &lt;run_id&gt; — Drive links\n"
        "/status — system status",
        parse_mode="HTML",
    )


@admin_only
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config_loader import sync_to_db
    from storage import database as db
    sync_to_db()

    # Read projects from monitors (since projects aren't listed in a separate list endpoint)
    monitors = db.list_monitors(enabled_only=False)
    project_ids = sorted({m.project_id for m in monitors})

    if not project_ids:
        await update.message.reply_text("No projects found. Check monitors.yaml")
        return

    lines = ["📁 <b>Projects</b>\n"]
    for pid in project_ids:
        p = db.get_project(pid)
        name = p.name if p else pid
        market = p.market if p else "—"
        enabled = "🟢" if (p and p.enabled) else "🔴"
        lines.append(f"{enabled} <b>{name}</b> (<code>{pid}</code>)")
        lines.append(f"   Market: {market}")
        # count monitors
        project_monitors = [m for m in monitors if m.project_id == pid]
        lines.append(f"   Monitors: {len(project_monitors)}")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def cmd_monitors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config_loader import sync_to_db
    from storage import database as db
    sync_to_db()
    monitors = db.list_monitors(enabled_only=False)
    if not monitors:
        await update.message.reply_text("No monitors found. Check monitors.yaml")
        return

    lines = [f"📡 <b>Monitors</b> ({len(monitors)} total)\n"]
    for m in monitors:
        status_dot = "🟢" if m.enabled else "🔴"
        last = db.get_last_run_for_monitor(m.id)
        last_str = ""
        if last:
            icon = _status_icon(last.status)
            last_str = (f"\n   Last run: {icon} {last.status} "
                        f"({last.total_posts}p/{last.total_comments}c) "
                        f"{(last.started_at or '')[:16]}")
        lines.append(
            f"{status_dot} <b>{m.name}</b>\n"
            f"   <code>{m.id}</code> [{m.project_id}]\n"
            f"   {m.run_mode} | <code>{m.schedule_cron}</code> {m.timezone}"
            f"{last_str}\n"
        )

    msg = "\n".join(lines)
    # Telegram message limit: 4096 chars
    if len(msg) > 4000:
        msg = msg[:3990] + "\n…(truncated)"
    await update.message.reply_text(msg, parse_mode="HTML")


@admin_only
async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config_loader import sync_to_db
    from storage import database as db
    from storage.models import Run, RUN_QUEUED
    sync_to_db()

    if not context.args:
        monitors = db.list_monitors(enabled_only=True)
        ids = " | ".join(m.id for m in monitors[:8])
        await update.message.reply_text(
            f"Usage: /run <monitor_id>\n\nEnabled monitors:\n<code>{ids}</code>",
            parse_mode="HTML",
        )
        return

    monitor_id = context.args[0].strip()
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        await update.message.reply_text(
            f"❌ Monitor '<code>{monitor_id}</code>' not found.\n"
            f"Use /monitors to see available monitors.",
            parse_mode="HTML",
        )
        return

    if not monitor.enabled:
        await update.message.reply_text(f"⚠️ Monitor <code>{monitor_id}</code> is disabled.")
        return

    active = db.get_active_run_for_monitor(monitor_id)
    if active:
        await update.message.reply_text(
            f"⚙️ Monitor <code>{monitor_id}</code> already running (run {active.id}).",
            parse_mode="HTML",
        )
        return

    # Create queued run immediately so user gets a run ID
    run_id = str(uuid.uuid4())[:12]
    run = Run(
        id=run_id,
        monitor_id=monitor_id,
        project_id=monitor.project_id,
        status=RUN_QUEUED,
        started_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.create_run(run)

    await update.message.reply_text(
        f"🚀 <b>Run started!</b>\n\n"
        f"📡 Monitor: <b>{monitor.name}</b>\n"
        f"🆔 Run ID: <code>{run_id}</code>\n\n"
        f"⏱ Parsing Reddit... takes 5–10 min.\n"
        f"I'll send results when done.",
        parse_mode="HTML",
    )

    # Execute in background (non-blocking)
    asyncio.create_task(
        _run_in_background(context.bot, update.effective_chat.id, monitor_id, run_id)
    )


@admin_only
async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import database as db
    db.init_db()
    monitors = db.list_monitors(enabled_only=False)
    if not monitors:
        await update.message.reply_text("No monitors found.")
        return

    lines = ["📊 <b>Latest Runs</b>\n"]
    for m in monitors:
        last = db.get_last_run_for_monitor(m.id)
        if last:
            lines.append(_format_run(last))
        else:
            lines.append(f"⬜ <code>{m.id}</code> — never ran\n")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def cmd_runs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import database as db
    db.init_db()

    limit = 10
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 50)

    runs = db.list_runs(limit=limit)
    if not runs:
        await update.message.reply_text(
            "No runs yet. Use /run <monitor_id> to start one."
        )
        return

    lines = [f"🕐 <b>Recent Runs</b> (last {len(runs)})\n"]
    for run in runs:
        lines.append(_format_run(run))

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def cmd_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import database as db
    db.init_db()

    if not context.args:
        await update.message.reply_text("Usage: /download <run_id>")
        return

    run_id = context.args[0].strip()
    run = db.get_run(run_id)
    if not run:
        await update.message.reply_text(f"❌ Run <code>{run_id}</code> not found.", parse_mode="HTML")
        return

    exports = db.list_exports_for_run(run_id)
    xlsx_exports = [e for e in exports if e.format == "xlsx"]

    if not xlsx_exports:
        await update.message.reply_text(
            f"No Excel file for run <code>{run_id}</code>.\n"
            f"Use /drive {run_id} for Drive links.",
            parse_mode="HTML",
        )
        return

    exp = xlsx_exports[0]

    # Try local file first
    local_path = exp.file_path
    if not (local_path and os.path.exists(local_path)):
        # Try to download from Drive
        if exp.drive_file_id:
            await update.message.reply_text("📥 Downloading from Google Drive...")
            try:
                from drive_uploader import download_file
                tmp_path = f"/tmp/{run_id}_report.xlsx"
                download_file(exp.drive_file_id, tmp_path)
                local_path = tmp_path
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Download from Drive failed: <code>{e}</code>",
                    parse_mode="HTML",
                )
                return
        else:
            await update.message.reply_text(
                "❌ File not available locally and not on Google Drive.\n"
                "The file may have been cleaned up."
            )
            return

    await update.message.reply_text(f"📤 Sending Excel file for run <code>{run_id}</code>...", parse_mode="HTML")
    try:
        with open(local_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"reddit_{run.monitor_id}_{run_id}.xlsx",
                caption=f"📊 Run {run_id} | {run.monitor_id} | {run.total_posts} posts",
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send file: <code>{e}</code>", parse_mode="HTML")


@admin_only
async def cmd_drive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import database as db
    db.init_db()

    if not context.args:
        await update.message.reply_text("Usage: /drive <run_id>")
        return

    run_id = context.args[0].strip()
    run = db.get_run(run_id)
    if not run:
        await update.message.reply_text(f"❌ Run <code>{run_id}</code> not found.", parse_mode="HTML")
        return

    exports = db.list_exports_for_run(run_id)
    drive_exports = [e for e in exports if e.drive_web_view_link]

    if not drive_exports:
        await update.message.reply_text(
            f"☁️ No Google Drive files for run <code>{run_id}</code>.\n"
            f"Drive may not be configured, or files were not uploaded.",
            parse_mode="HTML",
        )
        return

    lines = [
        f"☁️ <b>Google Drive — Run {run_id}</b>",
        f"📡 {run.monitor_id} | {run.total_posts} posts, {run.total_comments} comments\n",
    ]
    fmt_icons = {"xlsx": "📊", "json": "📄", "handoff_json": "🤖"}
    for exp in drive_exports:
        ico   = fmt_icons.get(exp.format, "📁")
        label = exp.format.upper().replace("_", " ")
        lines.append(f"{ico} <a href='{exp.drive_web_view_link}'>{label}</a>")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import database as db
    db.init_db()

    # DB check
    try:
        monitors = db.list_monitors()
        runs = db.list_runs(limit=1)
        db_info = f"✅ {'Postgres' if os.environ.get('DATABASE_URL') else 'SQLite'} ({len(monitors)} monitors)"
    except Exception as e:
        db_info = f"❌ Error: {e}"

    # Drive check
    from drive_uploader import DRIVE_ENABLED
    if DRIVE_ENABLED:
        try:
            from drive_uploader import _get_service
            _get_service()
            drive_info = "✅ Connected"
        except Exception as e:
            drive_info = f"❌ Error: {str(e)[:80]}"
    else:
        drive_info = "⚠️ Not configured (GOOGLE_DRIVE_FOLDER_ID not set)"

    env_info = "Railway" if os.environ.get("RAILWAY_ENVIRONMENT") else "Local"
    bot_info = f"✅ Running | Admin IDs: {_ADMIN_IDS_RAW or '(none set)'}"

    await update.message.reply_text(
        f"🔧 <b>System Status</b>\n\n"
        f"📦 <b>Database:</b> {db_info}\n"
        f"☁️ <b>Google Drive:</b> {drive_info}\n"
        f"🤖 <b>Bot:</b> {bot_info}\n"
        f"🌍 <b>Environment:</b> {env_info}\n"
        f"⏰ <b>Scheduler:</b> Railway cron (*/30 * * * * UTC)\n",
        parse_mode="HTML",
    )


# ── Unknown command ────────────────────────────────────────────────────────────

@admin_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Unknown command. Use /start to see available commands."
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    setup_logger("INFO")

    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)

    if not _ADMIN_IDS_RAW:
        logger.warning("ADMIN_TELEGRAM_IDS is not set — bot will deny all access!")

    # Init DB on startup
    try:
        from storage import database as db
        db.init_db()
        from config_loader import sync_to_db
        sync_to_db()
    except Exception as e:
        logger.error(f"DB init failed: {e}")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("monitors", cmd_monitors))
    app.add_handler(CommandHandler("run",      cmd_run))
    app.add_handler(CommandHandler("latest",   cmd_latest))
    app.add_handler(CommandHandler("runs",     cmd_runs))
    app.add_handler(CommandHandler("download", cmd_download))
    app.add_handler(CommandHandler("drive",    cmd_drive))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    logger.info("🤖 Telegram bot started. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
