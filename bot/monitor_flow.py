"""
/create_monitor <project_id> ConversationHandler
Steps:
  1. Name
  2. Description (skip optional)
  3. Subreddit preset or custom
  4. Keyword preset or custom
  5. Run mode
  6. Schedule
  7. Confirm + optional immediate run
"""
import json
import re
import uuid
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from loguru import logger

from bot.auth import admin_only, get_uid
from bot.keyboards import (
    preset_list, run_mode_choice,
    monitor_schedule_choice, monitor_cancel_confirm,
    cancel_button, skip_cancel, after_monitor_created, retry_project_id,
)
from bot.states import (
    CM_NAME, CM_DESC, CM_SUBREDDIT_CHOICE, CM_SUBREDDIT_CUSTOM,
    CM_KEYWORD_CHOICE, CM_KEYWORD_CUSTOM, CM_RUN_MODE, CM_SCHEDULE, CM_CONFIRM,
    CM_WAIT_PROJECT_ID,
)
from storage.models import Monitor, MAX_ACTIVE_MONITORS_PER_PROJECT
from storage import database as db


def _make_monitor_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())[:20].strip("_")
    return f"{slug}_{str(uuid.uuid4())[:6]}"


def _draft(context) -> dict:
    return context.user_data.setdefault("create_monitor", {})


def _clear(context):
    context.user_data.pop("create_monitor", None)


# ── Shared: validate project and kick off name step ───────────────────────────

async def _begin_monitor_for_project(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    project_id: str,
    *,
    is_callback: bool = False,
) -> int:
    """Validate project, set up draft, ask for monitor name. Returns next state."""
    uid = get_uid(update)
    project = db.get_project(project_id)

    reply = update.callback_query.edit_message_text if is_callback else update.message.reply_text

    if not project:
        await reply(
            f"❌ Проект <code>{project_id}</code> не найден.\n\n"
            f"Проверьте правильность ID или выберите из своих проектов:",
            parse_mode="HTML",
            reply_markup=retry_project_id(),
        )
        return CM_WAIT_PROJECT_ID  # stay — allow re-input

    if project.owner_telegram_id != uid and project.owner_telegram_id != 0:
        await reply("⛔ Это не ваш проект.", reply_markup=retry_project_id())
        return CM_WAIT_PROJECT_ID

    active_monitors = db.count_active_monitors(project_id)
    if active_monitors >= MAX_ACTIVE_MONITORS_PER_PROJECT:
        await reply(
            f"⚠️ В проекте уже {active_monitors} активных мониторов "
            f"(макс. {MAX_ACTIVE_MONITORS_PER_PROJECT}).\n"
            f"Архивируйте один перед созданием нового.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    _clear(context)
    _draft(context)["project_id"]   = project_id
    _draft(context)["project_name"] = project.name

    text = (
        f"📡 <b>Новый монитор</b> для проекта <b>{project.name}</b>\n\n"
        f"Шаг 1/7: Введите <b>название</b> монитора:\n"
        f"<i>Например: Wellness Hot, Rising trends, Monthly top</i>"
    )
    await reply(text, parse_mode="HTML", reply_markup=cancel_button())
    return CM_NAME


# ── Entry — /create_monitor [project_id] ──────────────────────────────────────

@admin_only
async def start_create_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry via command. Two modes:
      /create_monitor <project_id>  →  validate & start immediately
      /create_monitor               →  ask for project_id, enter CM_WAIT_PROJECT_ID
    """
    if context.args:
        return await _begin_monitor_for_project(update, context, context.args[0].strip())

    # No project_id — ask for it
    uid = get_uid(update)
    projects = db.list_projects(owner_telegram_id=uid)
    proj_list_text = ""
    if projects:
        proj_list_text = "\n\n<b>Ваши проекты:</b>\n" + "\n".join(
            f"• <code>{p.id}</code> — {p.name}" for p in projects[:5]
        )

    await update.message.reply_text(
        f"📡 <b>Создание монитора</b>\n\n"
        f"Введите <b>project_id</b> проекта, в котором создать монитор:"
        f"{proj_list_text}",
        parse_mode="HTML",
        reply_markup=cancel_button(),
    )
    return CM_WAIT_PROJECT_ID


# ── Entry — callback from inline button (proj:create_monitor:<id>) ─────────────

async def start_create_monitor_from_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry via inline button. callback_data = "proj:create_monitor:<project_id>"
    """
    query = update.callback_query
    await query.answer()
    project_id = query.data.split(":", 2)[2]
    return await _begin_monitor_for_project(
        update, context, project_id, is_callback=True
    )


# ── CM_WAIT_PROJECT_ID: receive project_id as text ────────────────────────────

async def handle_project_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receive project_id typed by user. Validates and proceeds to CM_NAME.
    Stays in CM_WAIT_PROJECT_ID if invalid.
    """
    project_id = update.message.text.strip()
    return await _begin_monitor_for_project(update, context, project_id)


# ── Step 1: Name ───────────────────────────────────────────────────────────────

async def handle_monitor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Слишком короткое. Минимум 2 символа:")
        return CM_NAME
    _draft(context)["name"] = name
    await update.message.reply_text(
        "Шаг 2/7: <b>Описание</b> монитора (необязательно):",
        parse_mode="HTML",
        reply_markup=skip_cancel(),
    )
    return CM_DESC


# ── Step 2: Description ────────────────────────────────────────────────────────

async def handle_monitor_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _draft(context)["description"] = update.message.text.strip()[:300]
    return await _ask_subreddit_preset(update, context)


async def skip_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _draft(context)["description"] = ""
    return await _ask_subreddit_preset(update, context)


async def _ask_subreddit_preset(update: Update, context):
    uid = get_uid(update)
    presets = db.list_subreddit_presets(owner_telegram_id=uid, include_system=True)
    msg = "Шаг 3/7: Выберите <b>subreddit preset</b> или введите вручную:"
    kb = preset_list(presets, "sr")
    await update.effective_message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    return CM_SUBREDDIT_CHOICE


# ── Step 3: Subreddit preset ───────────────────────────────────────────────────

async def handle_subreddit_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset_id = query.data.split(":", 1)[1]  # sr_preset:wellness_en → wellness_en

    if preset_id == "__custom__":
        await query.edit_message_text(
            "Введите сабреддиты через запятую:\n"
            "<i>Например: nutrition, Supplements, GutHealth, Sleep</i>",
            parse_mode="HTML",
            reply_markup=cancel_button(),
        )
        return CM_SUBREDDIT_CUSTOM

    _draft(context)["subreddit_preset_id"] = preset_id
    _draft(context)["custom_subreddits"] = "[]"
    return await _ask_keyword_preset(update, context)


async def handle_custom_subreddits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    subs = [s.strip() for s in raw.split(",") if s.strip()]
    if not subs:
        await update.message.reply_text("❌ Введите хотя бы один сабреддит:")
        return CM_SUBREDDIT_CUSTOM
    _draft(context)["subreddit_preset_id"] = None
    _draft(context)["custom_subreddits"] = json.dumps(subs)
    return await _ask_keyword_preset(update, context)


async def _ask_keyword_preset(update: Update, context):
    uid = get_uid(update)
    presets = db.list_keyword_presets(owner_telegram_id=uid, include_system=True)
    msg = "Шаг 4/7: Выберите <b>keyword preset</b> или введите вручную:"
    kb = preset_list(presets, "kw")
    await update.effective_message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    return CM_KEYWORD_CHOICE


# ── Step 4: Keyword preset ─────────────────────────────────────────────────────

async def handle_keyword_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset_id = query.data.split(":", 1)[1]

    if preset_id == "__custom__":
        await query.edit_message_text(
            "Введите ключевые слова через запятую:\n"
            "<i>Например: fatigue, energy, magnesium, gut health</i>",
            parse_mode="HTML",
            reply_markup=cancel_button(),
        )
        return CM_KEYWORD_CUSTOM

    _draft(context)["keyword_preset_id"] = preset_id
    _draft(context)["custom_keywords"] = "[]"
    return await _ask_run_mode(update, context)


async def handle_custom_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    kws = [k.strip() for k in raw.split(",") if k.strip()]
    if not kws:
        await update.message.reply_text("❌ Введите хотя бы одно ключевое слово:")
        return CM_KEYWORD_CUSTOM
    _draft(context)["keyword_preset_id"] = None
    _draft(context)["custom_keywords"] = json.dumps(kws)
    return await _ask_run_mode(update, context)


async def _ask_run_mode(update: Update, context):
    msg = "Шаг 5/7: Выберите <b>режим запуска</b>:"
    kb = run_mode_choice()
    await update.effective_message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    return CM_RUN_MODE


# ── Shared: build Monitor from draft and save to DB ────────────────────────────

async def _create_monitor_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Create monitor from current draft, persist to DB, show success message.
    Returns monitor_id. Always uses update.effective_message for the reply.
    Draft is cleared after creation.
    """
    from bot.schedule_utils import frequency_label
    draft = _draft(context)
    uid   = get_uid(update)

    monitor_id = _make_monitor_id(draft["name"])
    monitor = Monitor(
        id=monitor_id,
        project_id=draft["project_id"],
        owner_telegram_id=uid,
        name=draft["name"],
        description=draft.get("description", ""),
        subreddit_preset_id=draft.get("subreddit_preset_id"),
        keyword_preset_id=draft.get("keyword_preset_id"),
        custom_subreddits=draft.get("custom_subreddits", "[]"),
        custom_keywords=draft.get("custom_keywords", "[]"),
        run_mode=draft.get("run_mode", "hot_last_7d"),
        schedule_mode=draft.get("schedule_mode", "manual"),
        frequency=draft.get("frequency", "none"),
        schedule_cron=draft.get("schedule_cron", ""),
        next_run_at=draft.get("next_run_at"),
        timezone="UTC",
        min_days_between_runs=7,
        max_runs_per_month=4,
        require_manual_confirmation=True,
        enabled=True,
        archived=False,
    )
    db.create_monitor(monitor)
    _clear(context)
    logger.info(f"Monitor created: {monitor_id} in project {monitor.project_id} by user {uid}")

    # Resolve labels for success message
    sr_label  = draft.get("subreddit_preset_id") or "custom"
    kw_label  = draft.get("keyword_preset_id") or "custom"
    sr_custom = json.loads(draft.get("custom_subreddits", "[]"))
    kw_custom = json.loads(draft.get("custom_keywords", "[]"))
    if sr_custom:
        sr_label = f"custom ({len(sr_custom)} sub)"
    if kw_custom:
        kw_label = f"custom ({len(kw_custom)} kw)"
    sched_label = frequency_label(monitor.frequency, monitor.schedule_cron)

    text = (
        f"✅ <b>Монитор создан!</b>\n\n"
        f"📡 <b>{monitor.name}</b>\n"
        f"📁 Проект: <b>{monitor.project_id}</b>\n"
        f"🌐 Источник: Reddit\n"
        f"📂 Сабреддиты: {sr_label}\n"
        f"🔑 Ключевые слова: {kw_label}\n"
        f"⚙️ Режим: {monitor.run_mode}\n"
        f"🕒 Расписание: {sched_label}\n\n"
        f"<b>Что дальше?</b>"
    )
    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=after_monitor_created(monitor_id, monitor.project_id),
    )
    return monitor_id


# ── Step 5: Run mode ───────────────────────────────────────────────────────────

async def handle_run_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.split(":")[1]  # runmode:hot_last_7d → hot_last_7d
    _draft(context)["run_mode"] = mode
    await query.edit_message_text(
        "Шаг 6/6: <b>Расписание</b> запусков:\n\n"
        "<i>Выберите 'Только вручную' — монитор будет создан и запускается по кнопке.\n"
        "Или настройте автоматический запуск.</i>",
        parse_mode="HTML",
        reply_markup=monitor_schedule_choice(),
    )
    return CM_SCHEDULE


# ── Step 6: Schedule — main dispatcher (mon_sch:*) ────────────────────────────

async def handle_schedule_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles mon_sch:* callbacks on the schedule step."""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]   # mon_sch:manual → manual

    from bot.schedule_utils import compute_next_run_at
    draft = _draft(context)

    # ── Manual: create monitor immediately, no extra confirm step ─────────────
    if choice == "manual":
        draft["schedule_mode"] = "manual"
        draft["frequency"]     = "none"
        draft["schedule_cron"] = ""
        draft["next_run_at"]   = None
        await _create_monitor_now(update, context)
        return ConversationHandler.END

    # ── Biweekly: set schedule, show confirm ──────────────────────────────────
    if choice == "biweekly":
        draft["schedule_mode"] = "scheduled"
        draft["frequency"]     = "biweekly"
        draft["schedule_cron"] = ""
        draft["next_run_at"]   = compute_next_run_at("biweekly", "", "UTC")
        return await _show_confirm(update, context)

    # ── Weekly / Monthly: ask for day ─────────────────────────────────────────
    if choice in ("weekly", "monthly"):
        draft["_pending_schedule"] = choice
        if choice == "weekly":
            from bot.keyboards import schedule_weekday
            await query.edit_message_text(
                "Выберите <b>день недели</b>:",
                parse_mode="HTML",
                reply_markup=schedule_weekday(),
            )
        else:
            from bot.keyboards import schedule_day_of_month
            await query.edit_message_text(
                "Выберите <b>день месяца</b> (1–28):",
                parse_mode="HTML",
                reply_markup=schedule_day_of_month(),
            )
        return CM_SCHEDULE   # stay, wait for day selection

    # ── Back: return to run mode step ─────────────────────────────────────────
    if choice == "back":
        draft.pop("run_mode", None)
        await query.edit_message_text(
            "Шаг 5/6: Выберите <b>режим запуска</b>:",
            parse_mode="HTML",
            reply_markup=run_mode_choice(),
        )
        return CM_RUN_MODE

    # ── Cancel: ask for confirmation ──────────────────────────────────────────
    if choice == "cancel_full":
        await query.edit_message_text(
            "🛑 <b>Отменить создание монитора?</b>\n\n"
            "Вы уже заполнили несколько шагов.\n"
            "Все введённые данные будут потеряны.",
            parse_mode="HTML",
            reply_markup=monitor_cancel_confirm(),
        )
        return CM_SCHEDULE   # stay — awaiting mon_cancel:confirm or mon_cancel:back

    return CM_SCHEDULE


# ── Step 6: Schedule — day/time for weekly/monthly ────────────────────────────

async def handle_schedule_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle weekday or day-of-month selection."""
    query = update.callback_query
    await query.answer()
    draft = _draft(context)

    data = query.data   # sch_day:0 or sch_dom:15
    day = int(data.split(":")[1])
    draft["_schedule_day"] = day

    await query.edit_message_text(
        "Введите <b>время запуска</b> в формате HH:MM (UTC):\n"
        "<i>Например: 08:00</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Назад",         callback_data="mon_sch:back_day"),
            InlineKeyboardButton("🛑 Отменить",      callback_data="mon_sch:cancel_full"),
        ]]),
    )
    return CM_SCHEDULE


async def handle_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle time input for weekly/monthly schedule."""
    from bot.schedule_utils import parse_time, build_weekly_cron, build_monthly_cron, compute_next_run_at
    draft = _draft(context)
    pending = draft.get("_pending_schedule", "weekly")

    try:
        hour, minute = parse_time(update.message.text)
    except ValueError as e:
        await update.message.reply_text(
            f"❌ {e}\n<i>Введите время в формате HH:MM, например: 08:00</i>",
            parse_mode="HTML",
        )
        return CM_SCHEDULE

    day = draft.get("_schedule_day", 1)
    if pending == "weekly":
        cron = build_weekly_cron(day, hour, minute)
    else:
        cron = build_monthly_cron(day, hour, minute)

    draft["schedule_mode"] = "scheduled"
    draft["frequency"]     = pending
    draft["schedule_cron"] = cron
    draft["next_run_at"]   = compute_next_run_at(pending, cron, "UTC")
    draft.pop("_pending_schedule", None)
    draft.pop("_schedule_day", None)

    return await _show_confirm(update, context)


# ── Step 6: Cancel confirmation callbacks ─────────────────────────────────────

async def handle_cancel_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles mon_cancel:confirm and mon_cancel:back.
    Also handles mon_sch:back_day (back from day-of-week/month to schedule choice).
    """
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]   # mon_cancel:confirm → confirm

    if action == "confirm":
        _clear(context)
        await query.edit_message_text(
            "❌ Создание монитора отменено.\n\n"
            "Вернитесь в меню: /menu",
        )
        return ConversationHandler.END

    if action == "back":
        # Back from cancel-confirmation to schedule choice
        await query.edit_message_text(
            "Шаг 6/6: <b>Расписание</b> запусков:",
            parse_mode="HTML",
            reply_markup=monitor_schedule_choice(),
        )
        return CM_SCHEDULE

    return CM_SCHEDULE


async def handle_schedule_back_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back from day-input to schedule choice."""
    query = update.callback_query
    await query.answer()
    draft = _draft(context)
    draft.pop("_pending_schedule", None)
    draft.pop("_schedule_day", None)
    await query.edit_message_text(
        "Шаг 6/6: <b>Расписание</b> запусков:",
        parse_mode="HTML",
        reply_markup=monitor_schedule_choice(),
    )
    return CM_SCHEDULE


# ── Step 7: Confirm (for scheduled monitors) ──────────────────────────────────

async def _show_confirm(update: Update, context):
    from bot.schedule_utils import frequency_label
    draft = _draft(context)

    sr_label  = draft.get("subreddit_preset_id") or "custom"
    kw_label  = draft.get("keyword_preset_id") or "custom"
    sr_custom = json.loads(draft.get("custom_subreddits", "[]"))
    kw_custom = json.loads(draft.get("custom_keywords", "[]"))
    if sr_custom:
        sr_label = f"custom ({len(sr_custom)} sub)"
    if kw_custom:
        kw_label = f"custom ({len(kw_custom)} kw)"

    sched_label = frequency_label(draft.get("frequency", "none"), draft.get("schedule_cron", ""))
    next_run    = draft.get("next_run_at") or "—"

    summary = (
        f"<b>Подтвердите создание монитора:</b>\n\n"
        f"📡 <b>Название:</b> {draft.get('name')}\n"
        f"📁 <b>Проект:</b> {draft.get('project_name')}\n"
        f"🌐 <b>Сабреддиты:</b> {sr_label}\n"
        f"🔑 <b>Ключевые слова:</b> {kw_label}\n"
        f"⚙️ <b>Режим:</b> {draft.get('run_mode')}\n"
        f"🕒 <b>Расписание:</b> {sched_label}\n"
        f"📅 <b>Следующий запуск:</b> {next_run[:16] if next_run != '—' else '—'}\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Создать",          callback_data="mon_confirm:yes")],
        [InlineKeyboardButton("⬅️ Назад к расписанию", callback_data="mon_confirm:back_sched")],
        [InlineKeyboardButton("🛑 Отменить создание", callback_data="mon_sch:cancel_full")],
    ])
    await update.effective_message.reply_text(summary, parse_mode="HTML", reply_markup=kb)
    return CM_CONFIRM


async def handle_monitor_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]   # mon_confirm:yes or mon_confirm:back_sched

    if action == "back_sched":
        # Go back to schedule step
        await query.edit_message_text(
            "Шаг 6/6: <b>Расписание</b> запусков:",
            parse_mode="HTML",
            reply_markup=monitor_schedule_choice(),
        )
        return CM_SCHEDULE

    # action == "yes" → create
    await _create_monitor_now(update, context)
    return ConversationHandler.END


# ── Cancel (fallback: /cancel command) ────────────────────────────────────────

async def cancel_create_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fallback for /cancel command.
    If the user has already filled in the monitor name (i.e. serious progress),
    ask for confirmation before discarding. Otherwise cancel immediately.
    """
    draft = _draft(context)
    has_progress = bool(draft.get("name"))

    if has_progress:
        # Ask confirmation — return CM_SCHEDULE so mon_cancel:* callbacks are handled
        await update.message.reply_text(
            "⚠️ <b>Вы уже заполнили несколько шагов.</b>\n\n"
            "Отменить создание монитора полностью?\n"
            "Все введённые данные будут потеряны.",
            parse_mode="HTML",
            reply_markup=monitor_cancel_confirm(),
        )
        return CM_SCHEDULE   # stay alive so mon_cancel: callbacks fire

    # No meaningful progress — cancel right away
    _clear(context)
    await update.message.reply_text(
        "❌ Создание монитора отменено.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")
        ]]),
    )
    return ConversationHandler.END


# ── Retry pid button handler (stays in CM_WAIT_PROJECT_ID) ────────────────────

async def _cb_retry_pid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Введите <b>project_id</b> проекта ещё раз:",
        parse_mode="HTML",
        reply_markup=cancel_button(),
    )
    return CM_WAIT_PROJECT_ID


# ── ConversationHandler factory ────────────────────────────────────────────────

def build_create_monitor_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("create_monitor", start_create_monitor),
            CallbackQueryHandler(start_create_monitor_from_cb, pattern=r"^proj:create_monitor:"),
        ],
        states={
            CM_WAIT_PROJECT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_project_id_input),
                CallbackQueryHandler(_cb_retry_pid, pattern=r"^mon:retry_pid$"),
            ],
            CM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_monitor_name)],
            CM_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_monitor_desc),
                CallbackQueryHandler(skip_desc, pattern="^skip$"),
            ],
            CM_SUBREDDIT_CHOICE: [CallbackQueryHandler(handle_subreddit_preset, pattern="^sr_preset:")],
            CM_SUBREDDIT_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_subreddits)],
            CM_KEYWORD_CHOICE:   [CallbackQueryHandler(handle_keyword_preset, pattern="^kw_preset:")],
            CM_KEYWORD_CUSTOM:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_keywords)],
            CM_RUN_MODE: [
                CallbackQueryHandler(handle_run_mode, pattern="^runmode:"),
            ],
            CM_SCHEDULE: [
                # Main schedule choice (mon_sch:manual/weekly/biweekly/monthly/back/cancel_full/back_day)
                CallbackQueryHandler(handle_schedule_choice,   pattern=r"^mon_sch:(?!back_day)"),
                CallbackQueryHandler(handle_schedule_back_day, pattern=r"^mon_sch:back_day$"),
                # Cancel confirmation (mon_cancel:confirm / mon_cancel:back)
                CallbackQueryHandler(handle_cancel_confirm_cb, pattern=r"^mon_cancel:"),
                # Day/time sub-steps
                CallbackQueryHandler(handle_schedule_day, pattern=r"^(sch_day|sch_dom):"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_time),
            ],
            CM_CONFIRM: [
                # mon_confirm:yes → create; mon_confirm:back_sched → back to schedule
                CallbackQueryHandler(handle_monitor_confirm, pattern=r"^mon_confirm:"),
                # Allow cancel_full from confirm step too
                CallbackQueryHandler(handle_schedule_choice,  pattern=r"^mon_sch:cancel_full$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_create_monitor),
            # cancel_conv is still sent by some early-step cancel_button() keyboards
            CallbackQueryHandler(cancel_create_monitor, pattern="^cancel_conv$"),
        ],
        allow_reentry=True,
        name="create_monitor",
        persistent=False,
    )
