"""
All non-conversation bot commands and callback handlers.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from loguru import logger
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from bot.auth import admin_only, get_uid
from bot.keyboards import (
    main_menu, project_list, project_menu, monitor_list, monitor_menu,
    run_confirm_keyboard, confirm_archive, schedule_frequency,
)
from bot.schedule_utils import days_since_run, frequency_label
from storage import database as db
from storage.models import Run, RUN_QUEUED


# ── Formatters ─────────────────────────────────────────────────────────────────

def _status_icon(status: str) -> str:
    return {"queued": "📋", "running": "⚙️", "completed": "✅",
            "completed_with_warning": "⚠️", "failed": "❌"}.get(status, "❓")


def _fmt_run(run: Run) -> str:
    icon = _status_icon(run.status)
    q    = "✅" if run.quality_status == "ok" else "⚠️"
    return (
        f"{icon} <code>{run.id}</code> | <b>{run.monitor_id}</b>\n"
        f"   {q} {run.total_posts}p / {run.total_comments}c"
        f"  🕐 {(run.started_at or '')[:16]}\n"
    )


def _fmt_run_result(run: Run, exports) -> str:
    icon = _status_icon(run.status)
    lines = [
        f"{icon} <b>Run {run.status.upper()}</b>",
        f"",
        f"🏷 <b>Проект:</b> {run.project_id}",
        f"📡 <b>Монитор:</b> {run.monitor_id}",
        f"🆔 <b>Run ID:</b> <code>{run.id}</code>",
        f"",
        f"📊 <b>Постов:</b> {run.total_posts}",
        f"💬 <b>Комментариев:</b> {run.total_comments}",
        f"🔬 <b>Качество:</b> {'✅ ok' if run.quality_status == 'ok' else '⚠️ ' + run.quality_status}",
    ]
    if run.warning_message:
        lines.append(f"⚠️ {run.warning_message}")

    if run.top_keywords_json:
        try:
            kws = json.loads(run.top_keywords_json)
            kw_str = ", ".join(f"{k['keyword']} ({k['total_mentions']})" for k in kws[:6])
            lines += ["", f"🔑 <b>Топ ключевых слов:</b>", f"   {kw_str}"]
        except Exception:
            pass

    drive_exports = [e for e in exports if e.drive_web_view_link]
    if drive_exports:
        fmt_icons = {"xlsx": "📊", "json": "📄", "handoff_json": "🤖"}
        lines += ["", "☁️ <b>Google Drive:</b>"]
        for exp in drive_exports:
            ico   = fmt_icons.get(exp.format, "📁")
            label = exp.format.upper().replace("_", " ")
            lines.append(f"   {ico} <a href='{exp.drive_web_view_link}'>{label}</a>")
    elif run.export_path:
        lines += ["", f"📁 <b>Локальный экспорт:</b> <code>{run.export_path}</code>"]

    if run.status == "failed" and run.error_message:
        lines += ["", f"💥 <b>Ошибка:</b> <code>{run.error_message[:200]}</code>"]

    return "\n".join(lines)


# ── /start ─────────────────────────────────────────────────────────────────────

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "там"
    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        f"<b>Trend Intelligence Hub</b> — мониторинг Reddit-трендов.\n\n"
        f"📁 Создавайте проекты под любые ниши\n"
        f"📡 Настраивайте мониторы с расписанием\n"
        f"☁️ Файлы сохраняются в Google Drive\n"
        f"🤖 AI Handoff JSON для анализа\n\n"
        f"<b>Команды:</b>\n"
        f"/projects — мои проекты\n"
        f"/create_project — создать проект\n"
        f"/status — статус системы\n"
        f"/runs — история запусков",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ── /projects ──────────────────────────────────────────────────────────────────

@admin_only
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    projects = db.list_projects(owner_telegram_id=uid)
    if not projects:
        await update.message.reply_text(
            "У вас ещё нет проектов.\n\nСоздайте первый:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Создать проект", callback_data="menu:create_project")
            ]]),
        )
        return

    lines = [f"📁 <b>Мои проекты</b> ({len(projects)})\n"]
    for p in projects:
        m_count = db.count_active_monitors(p.id)
        icon = "🗄" if p.archived else "📁"
        lines.append(
            f"{icon} <b>{p.name}</b>\n"
            f"   <code>{p.id}</code>  •  {m_count} мониторов  •  {p.output_language.upper()}\n"
        )
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=project_list(projects),
    )


# ── /monitors ──────────────────────────────────────────────────────────────────

@admin_only
async def cmd_monitors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = get_uid(update)
    args  = context.args
    pid   = args[0] if args else None

    monitors = db.list_monitors(project_id=pid, owner_telegram_id=uid if not pid else None)
    if not monitors:
        msg = "Нет мониторов." + (f"\nСоздайте: /create_monitor {pid}" if pid else "")
        await update.message.reply_text(msg)
        return

    lines = [f"📡 <b>Мониторы</b> ({len(monitors)})\n"]
    for m in monitors:
        icon  = "🟢" if m.enabled and not m.archived else "🔴"
        sched = frequency_label(m.frequency, m.schedule_cron)
        last  = db.get_last_run_for_monitor(m.id)
        last_str = ""
        if last:
            last_str = f"\n   Последний: {_status_icon(last.status)} {last.total_posts}p/{last.total_comments}c {(last.started_at or '')[:16]}"
        lines.append(
            f"{icon} <b>{m.name}</b> [<code>{m.id}</code>]\n"
            f"   {m.run_mode} | {sched}{last_str}\n"
        )
    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3990] + "\n…(обрезано)"
    await update.message.reply_text(msg, parse_mode="HTML")


# ── /run <monitor_id> ──────────────────────────────────────────────────────────

@admin_only
async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        uid  = get_uid(update)
        mons = db.list_monitors(owner_telegram_id=uid, enabled_only=True)
        ids  = " | ".join(m.id for m in mons[:6])
        await update.message.reply_text(
            f"Использование: /run <monitor_id>\n\nДоступные мониторы:\n<code>{ids}</code>",
            parse_mode="HTML",
        )
        return

    monitor_id = context.args[0].strip()
    await _trigger_run(update, context, monitor_id, force=False)


async def _trigger_run(update, context, monitor_id: str, force: bool = False):
    """Check constraints, show warning if needed, or queue the run."""
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        target = update.message or update.callback_query.message
        await target.reply_text(f"❌ Монитор <code>{monitor_id}</code> не найден.", parse_mode="HTML")
        return

    if monitor.archived or not monitor.enabled:
        target = update.message or update.callback_query.message
        await target.reply_text("⚠️ Монитор отключён или в архиве.")
        return

    if monitor.schedule_mode == "disabled":
        target = update.message or update.callback_query.message
        await target.reply_text(
            "🚫 Монитор отключён. Включите его через /schedule или /edit_monitor."
        )
        return

    # Active run check
    active = db.get_active_run_for_monitor(monitor_id)
    if active:
        target = update.message or update.callback_query.message
        await target.reply_text(
            f"⚙️ Монитор уже запущен (run {active.id}).",
            parse_mode="HTML",
        )
        return

    # Min days protection
    if not force and monitor.min_days_between_runs > 0:
        days = days_since_run(monitor.last_run_at)
        if days is not None and days < monitor.min_days_between_runs:
            remaining = monitor.min_days_between_runs - days
            target = update.message or update.callback_query.message
            await target.reply_text(
                f"⚠️ <b>Внимание!</b>\n\n"
                f"Монитор <b>{monitor.name}</b> запускался {days} дн. назад.\n"
                f"Лимит: {monitor.min_days_between_runs} дней между запусками.\n"
                f"Осталось: <b>{remaining} дн.</b>\n\n"
                f"Повторный запуск может создать дубликаты данных.",
                parse_mode="HTML",
                reply_markup=run_confirm_keyboard(monitor_id, force=True),
            )
            return

    # Queue and run
    await _queue_and_run(update, context, monitor, monitor_id)


async def _queue_and_run(update, context, monitor, monitor_id: str):
    run_id = str(uuid.uuid4())[:12]
    run = Run(
        id=run_id,
        monitor_id=monitor_id,
        project_id=monitor.project_id,
        status=RUN_QUEUED,
        started_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.create_run(run)

    chat_id = update.effective_chat.id
    target = update.message or update.callback_query.message
    await target.reply_text(
        f"🚀 <b>Запуск начат!</b>\n\n"
        f"📡 <b>{monitor.name}</b>\n"
        f"🆔 Run ID: <code>{run_id}</code>\n\n"
        f"⏱ Парсинг Reddit занимает 5–10 минут.\n"
        f"Результаты пришлю сюда.",
        parse_mode="HTML",
    )
    asyncio.create_task(_background_run(context.bot, chat_id, monitor_id, run_id))


async def _background_run(bot, chat_id: int, monitor_id: str, run_id: str):
    from monitor_runner import run_monitor
    try:
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(
            None, lambda: run_monitor(monitor_id, existing_run_id=run_id)
        )
        if run:
            exports = db.list_exports_for_run(run.id)
            msg = _fmt_run_result(run, exports)
        else:
            msg = f"❌ Запуск не удался для <code>{monitor_id}</code>"
        await bot.send_message(chat_id=chat_id, text=msg,
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.exception(f"Background run failed: {e}")
        await bot.send_message(chat_id=chat_id,
                               text=f"❌ Run crashed: <code>{str(e)[:300]}</code>",
                               parse_mode="HTML")


# ── /schedule <monitor_id> ─────────────────────────────────────────────────────

@admin_only
async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /schedule <monitor_id>")
        return
    monitor_id = context.args[0].strip()
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        await update.message.reply_text(f"❌ Монитор не найден: {monitor_id}")
        return

    context.user_data["schedule_monitor_id"] = monitor_id
    await update.message.reply_text(
        f"🕒 <b>Расписание монитора</b> <code>{monitor.name}</code>\n\n"
        f"Текущее: {frequency_label(monitor.frequency, monitor.schedule_cron)}\n\n"
        f"Выберите новое расписание:",
        parse_mode="HTML",
        reply_markup=schedule_frequency(),
    )


# ── /next_runs ─────────────────────────────────────────────────────────────────

@admin_only
async def cmd_next_runs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = get_uid(update)
    mons = db.list_monitors(owner_telegram_id=uid, enabled_only=True)
    if not mons:
        await update.message.reply_text("Нет активных мониторов.")
        return

    lines = ["🗓 <b>Следующие запуски</b>\n"]
    for m in mons:
        sched = frequency_label(m.frequency, m.schedule_cron)
        if m.schedule_mode == "scheduled" and m.next_run_at:
            lines.append(f"📡 <b>{m.name}</b>\n   📅 {m.next_run_at[:16]} UTC ({sched})\n")
        elif m.schedule_mode == "disabled":
            lines.append(f"📡 <b>{m.name}</b>\n   🚫 Отключён\n")
        else:
            lines.append(f"📡 <b>{m.name}</b>\n   👆 Только вручную\n")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── /runs ──────────────────────────────────────────────────────────────────────

@admin_only
async def cmd_runs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    limit = 10
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 50)
    uid  = get_uid(update)
    runs = db.list_runs(limit=limit)
    if not runs:
        await update.message.reply_text("Запусков ещё нет. /run <monitor_id>")
        return
    lines = [f"🕐 <b>Последние запуски</b> ({len(runs)})\n"]
    for r in runs:
        lines.append(_fmt_run(r))
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── /latest ────────────────────────────────────────────────────────────────────

@admin_only
async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = get_uid(update)
    mons = db.list_monitors(owner_telegram_id=uid)
    if not mons:
        await update.message.reply_text("Нет мониторов.")
        return
    lines = ["📊 <b>Последние запуски по мониторам</b>\n"]
    for m in mons:
        last = db.get_last_run_for_monitor(m.id)
        if last:
            lines.append(_fmt_run(last))
        else:
            lines.append(f"⬜ <code>{m.id}</code> — не запускался\n")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── /download <run_id> ─────────────────────────────────────────────────────────

@admin_only
async def cmd_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /download <run_id>")
        return
    run_id = context.args[0].strip()
    run = db.get_run(run_id)
    if not run:
        await update.message.reply_text(f"❌ Run {run_id} не найден.")
        return

    exports = db.list_exports_for_run(run_id)
    xlsx = next((e for e in exports if e.format == "xlsx"), None)
    if not xlsx:
        await update.message.reply_text(f"Нет Excel-файла для run {run_id}.")
        return

    local = xlsx.file_path
    if not (local and os.path.exists(local)):
        if xlsx.drive_file_id:
            await update.message.reply_text("📥 Скачиваю из Google Drive...")
            try:
                from drive_uploader import download_file
                local = f"/tmp/{run_id}.xlsx"
                download_file(xlsx.drive_file_id, local)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка загрузки из Drive: {e}")
                return
        else:
            await update.message.reply_text("❌ Файл недоступен локально и не загружен в Drive.")
            return

    try:
        with open(local, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"reddit_{run.monitor_id}_{run_id}.xlsx",
                caption=f"📊 Run {run_id} | {run.monitor_id} | {run.total_posts} постов",
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки: {e}")


# ── /drive <run_id> ────────────────────────────────────────────────────────────

@admin_only
async def cmd_drive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /drive <run_id>")
        return
    run_id = context.args[0].strip()
    run = db.get_run(run_id)
    if not run:
        await update.message.reply_text(f"❌ Run {run_id} не найден.")
        return
    exports = db.list_exports_for_run(run_id)
    drive = [e for e in exports if e.drive_web_view_link]
    if not drive:
        await update.message.reply_text(
            f"☁️ Файлы для run {run_id} не загружены в Google Drive.\n"
            f"Возможно Drive не настроен или файлы ещё в процессе загрузки."
        )
        return
    lines = [f"☁️ <b>Google Drive — Run {run_id}</b>",
             f"📡 {run.monitor_id} | {run.total_posts}p / {run.total_comments}c\n"]
    fmt_icons = {"xlsx": "📊", "json": "📄", "handoff_json": "🤖"}
    for exp in drive:
        ico   = fmt_icons.get(exp.format, "📁")
        label = exp.format.upper().replace("_", " ")
        lines.append(f"{ico} <a href='{exp.drive_web_view_link}'>{label}</a>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


# ── /presets ───────────────────────────────────────────────────────────────────

@admin_only
async def cmd_presets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    sr_presets = db.list_subreddit_presets(owner_telegram_id=uid, include_system=True)
    kw_presets = db.list_keyword_presets(owner_telegram_id=uid, include_system=True)

    lines = ["📋 <b>Доступные пресеты</b>\n",
             f"<b>🌐 Subreddit presets</b> ({len(sr_presets)}):"]
    for p in sr_presets:
        icon = "🔧" if p.is_system else "👤"
        subs = json.loads(p.subreddits) if p.subreddits else []
        lines.append(f"  {icon} <code>{p.id}</code> — {p.name} ({len(subs)} sub)")

    lines.append(f"\n<b>🔑 Keyword presets</b> ({len(kw_presets)}):")
    for p in kw_presets:
        icon = "🔧" if p.is_system else "👤"
        kws  = json.loads(p.keywords) if p.keywords else []
        lines.append(f"  {icon} <code>{p.id}</code> — {p.name} ({len(kws)} kw)")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── /status ────────────────────────────────────────────────────────────────────

@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        db.init_db()
        mons = db.list_monitors()
        db_ok = f"✅ {'Postgres' if os.environ.get('DATABASE_URL') else 'SQLite'} ({len(mons)} мониторов)"
    except Exception as e:
        db_ok = f"❌ {str(e)[:60]}"

    from drive_uploader import DRIVE_ENABLED
    drive_ok = "✅ Настроен" if DRIVE_ENABLED else "⚠️ Не настроен"

    env = "Railway" if os.environ.get("RAILWAY_ENVIRONMENT") else "Локальный"
    await update.message.reply_text(
        f"🔧 <b>Статус системы</b>\n\n"
        f"📦 <b>База данных:</b> {db_ok}\n"
        f"☁️ <b>Google Drive:</b> {drive_ok}\n"
        f"🌍 <b>Окружение:</b> {env}\n"
        f"⏰ <b>Scheduler:</b> Railway cron (*/30 * * * * UTC)\n",
        parse_mode="HTML",
    )


# ── Callback handlers for inline buttons ──────────────────────────────────────

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "menu:projects"
    action = data.split(":")[1]

    if action == "projects":
        uid = get_uid(update)
        projects = db.list_projects(owner_telegram_id=uid)
        if not projects:
            await query.edit_message_text(
                "У вас нет проектов. Создайте первый:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("➕ Создать проект", callback_data="menu:create_project")
                ]]),
            )
        else:
            lines = [f"📁 <b>Мои проекты</b> ({len(projects)})\n"]
            for p in projects:
                lines.append(f"📁 <b>{p.name}</b> [<code>{p.id}</code>]")
            await query.edit_message_text(
                "\n".join(lines), parse_mode="HTML",
                reply_markup=project_list(projects),
            )
    elif action == "create_project":
        await query.edit_message_text(
            "Используйте команду /create_project для создания проекта."
        )
    elif action == "runs":
        runs = db.list_runs(limit=5)
        if not runs:
            await query.edit_message_text("Нет запусков.")
        else:
            lines = ["🕐 <b>Последние запуски</b>\n"]
            for r in runs:
                lines.append(_fmt_run(r))
            await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    elif action == "status":
        await query.edit_message_text("Используйте /status для подробной информации.")


async def handle_proj_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts  = query.data.split(":")   # proj:open:project123
    action = parts[1]
    pid    = parts[2] if len(parts) > 2 else None

    if action == "open":
        p = db.get_project(pid)
        if not p:
            await query.edit_message_text("❌ Проект не найден.")
            return
        m_count = db.count_active_monitors(pid)
        last_run = db.list_runs(limit=1, project_id=pid)
        last_str = f"\n🕐 Последний запуск: {last_run[0].started_at[:16]}" if last_run else ""
        await query.edit_message_text(
            f"📁 <b>{p.name}</b>\n"
            f"🆔 <code>{p.id}</code>\n"
            f"🎯 Ниша: {p.niche or '—'}\n"
            f"🌐 Язык: {p.output_language.upper()}\n"
            f"📡 Мониторов: {m_count}{last_str}",
            parse_mode="HTML",
            reply_markup=project_menu(pid),
        )
    elif action == "monitors":
        monitors = db.list_monitors(project_id=pid)
        await query.edit_message_text(
            f"📡 <b>Мониторы проекта</b>",
            parse_mode="HTML",
            reply_markup=monitor_list(monitors, pid),
        )
    elif action == "create_monitor":
        await query.edit_message_text(
            f"Используйте: /create_monitor {pid}"
        )
    elif action == "archive":
        p = db.get_project(pid)
        await query.edit_message_text(
            f"Архивировать проект <b>{p.name if p else pid}</b>?\n"
            f"Все мониторы будут остановлены.",
            parse_mode="HTML",
            reply_markup=confirm_archive("project", pid),
        )


async def handle_mon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts  = query.data.split(":")
    action = parts[1]
    mid    = parts[2] if len(parts) > 2 else None

    if action == "open":
        m = db.get_monitor(mid)
        if not m:
            await query.edit_message_text("❌ Монитор не найден.")
            return
        last = db.get_last_run_for_monitor(mid)
        last_str = f"\n🕐 {_status_icon(last.status)} {last.total_posts}p/{last.total_comments}c {(last.started_at or '')[:16]}" if last else "\n🕐 Не запускался"
        sched = frequency_label(m.frequency, m.schedule_cron)
        await query.edit_message_text(
            f"📡 <b>{m.name}</b>\n"
            f"🆔 <code>{m.id}</code>\n"
            f"⚙️ {m.run_mode} | {sched}{last_str}",
            parse_mode="HTML",
            reply_markup=monitor_menu(mid),
        )
    elif action == "run":
        await _trigger_run(update, context, mid, force=False)
    elif action == "schedule":
        m = db.get_monitor(mid)
        context.user_data["schedule_monitor_id"] = mid
        await query.edit_message_text(
            f"🕒 Расписание: <b>{m.name if m else mid}</b>\n"
            f"Текущее: {frequency_label(m.frequency, m.schedule_cron) if m else '—'}",
            parse_mode="HTML",
            reply_markup=schedule_frequency(),
        )
    elif action == "archive":
        m = db.get_monitor(mid)
        await query.edit_message_text(
            f"Архивировать монитор <b>{m.name if m else mid}</b>?",
            parse_mode="HTML",
            reply_markup=confirm_archive("monitor", mid),
        )
    elif action == "runs":
        runs = db.list_runs(limit=5, monitor_id=mid)
        if not runs:
            await query.edit_message_text(f"Нет запусков для монитора {mid}.")
        else:
            lines = [f"🕐 <b>Запуски</b> для <code>{mid}</code>\n"]
            for r in runs:
                lines.append(_fmt_run(r))
            await query.edit_message_text("\n".join(lines), parse_mode="HTML")


async def handle_run_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle run_start:, run_force: callbacks."""
    query = update.callback_query
    await query.answer()
    parts     = query.data.split(":")
    action    = parts[0]
    monitor_id = parts[1] if len(parts) > 1 else None

    if not monitor_id:
        return

    monitor = db.get_monitor(monitor_id)
    if not monitor:
        await query.edit_message_text(f"❌ Монитор {monitor_id} не найден.")
        return

    force = (action == "run_force")
    if not force:
        # Normal run_start — check constraints
        await _trigger_run(update, context, monitor_id, force=False)
    else:
        # Forced run
        await _queue_and_run(update, context, monitor, monitor_id)


async def handle_archive_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts  = query.data.split(":")   # confirm_archive:project:project123
    entity = parts[1]
    eid    = parts[2]
    if entity == "project":
        db.archive_project(eid)
        await query.edit_message_text(f"🗄 Проект <code>{eid}</code> архивирован.", parse_mode="HTML")
    elif entity == "monitor":
        db.archive_monitor(eid)
        await query.edit_message_text(f"🗄 Монитор <code>{eid}</code> архивирован.", parse_mode="HTML")


async def handle_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle schedule frequency selection from monitor menu."""
    query      = update.callback_query
    await query.answer()
    monitor_id = context.user_data.get("schedule_monitor_id")
    if not monitor_id:
        await query.edit_message_text("❌ Монитор не выбран. Используйте /schedule <monitor_id>")
        return

    choice = query.data.split(":")[1]
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        await query.edit_message_text("❌ Монитор не найден.")
        return

    from bot.schedule_utils import frequency_label, compute_next_run_at
    if choice == "manual":
        monitor.schedule_mode = "manual"
        monitor.frequency     = "none"
        monitor.schedule_cron = ""
        monitor.next_run_at   = None
        db.update_monitor(monitor)
        await query.edit_message_text(
            f"✅ <b>{monitor.name}</b>: расписание → 👆 Только вручную",
            parse_mode="HTML",
        )
    elif choice == "disabled":
        monitor.schedule_mode = "disabled"
        monitor.frequency     = "none"
        monitor.schedule_cron = ""
        monitor.next_run_at   = None
        db.update_monitor(monitor)
        await query.edit_message_text(
            f"✅ <b>{monitor.name}</b>: расписание → 🚫 Отключён",
            parse_mode="HTML",
        )
    elif choice == "biweekly":
        monitor.schedule_mode = "scheduled"
        monitor.frequency     = "biweekly"
        monitor.schedule_cron = ""
        monitor.next_run_at   = compute_next_run_at("biweekly", "", monitor.timezone)
        db.update_monitor(monitor)
        await query.edit_message_text(
            f"✅ <b>{monitor.name}</b>: расписание → 📅 Раз в 2 недели\n"
            f"Следующий запуск: {(monitor.next_run_at or '—')[:16]}",
            parse_mode="HTML",
        )
    else:
        # weekly or monthly — need to ask for day + time
        context.user_data["_pending_schedule_type"] = choice
        if choice == "weekly":
            from bot.keyboards import schedule_weekday
            await query.edit_message_text(
                "Выберите день недели:", reply_markup=schedule_weekday()
            )
        else:
            from bot.keyboards import schedule_day_of_month
            await query.edit_message_text(
                "Выберите день месяца (1–28):", reply_markup=schedule_day_of_month()
            )


async def handle_schedule_day_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    day = int(query.data.split(":")[1])
    context.user_data["_schedule_day"] = day
    await query.edit_message_text(
        "Введите время запуска (HH:MM, UTC):\n<i>Например: 08:00</i>",
        parse_mode="HTML",
    )


async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Отменено.")
    await query.edit_message_text("✅ Действие отменено.")


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Неизвестная команда. /start — чтобы увидеть все команды."
    )
