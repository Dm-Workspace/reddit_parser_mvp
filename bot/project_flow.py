"""
/create_project ConversationHandler
Steps:
  1. Name
  2. Description (optional)
  3. Niche / market
  4. Output language  [inline buttons]
  5. Confirm          [inline buttons]
"""
import re
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from loguru import logger

from bot.auth import admin_only, get_uid
from bot.keyboards import language_choice, yes_no, cancel_button, after_project_created
from bot.states import CP_NAME, CP_DESC, CP_NICHE, CP_LANG, CP_CONFIRM
from storage.models import Project, MAX_ACTIVE_PROJECTS_PER_USER
from storage import database as db


def _make_project_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())[:20].strip("_")
    return f"{slug}_{str(uuid.uuid4())[:6]}"


def _draft(context) -> dict:
    return context.user_data.setdefault("create_project", {})


def _clear(context):
    context.user_data.pop("create_project", None)


# ── Entry ──────────────────────────────────────────────────────────────────────

@admin_only
async def start_create_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    active = db.count_active_projects(uid)
    if active >= MAX_ACTIVE_PROJECTS_PER_USER:
        await update.message.reply_text(
            f"⚠️ У вас уже {active} активных проектов (макс. {MAX_ACTIVE_PROJECTS_PER_USER}).\n"
            f"Архивируйте один из существующих проектов перед созданием нового.\n"
            f"Используйте /projects чтобы посмотреть проекты."
        )
        return ConversationHandler.END

    _clear(context)
    await update.message.reply_text(
        "📁 <b>Создание нового проекта</b>\n\n"
        "Шаг 1/4: Введите <b>название</b> проекта:\n"
        "<i>Например: Wellness и здоровье, CRM-автоматизация, AI-агенты</i>",
        parse_mode="HTML",
        reply_markup=cancel_button(),
    )
    return CP_NAME


# ── Step 1: Name ───────────────────────────────────────────────────────────────

async def handle_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Введите минимум 2 символа:")
        return CP_NAME
    if len(name) > 80:
        await update.message.reply_text("❌ Слишком длинное. Максимум 80 символов:")
        return CP_NAME

    _draft(context)["name"] = name
    await update.message.reply_text(
        f"Шаг 2/4: <b>Описание</b> проекта (необязательно):\n"
        f"<i>Что вы мониторите и зачем?</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭ Пропустить", callback_data="skip"),
            InlineKeyboardButton("❌ Отмена",     callback_data="cancel_conv"),
        ]]),
    )
    return CP_DESC


# ── Step 2: Description ────────────────────────────────────────────────────────

async def handle_project_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _draft(context)["description"] = update.message.text.strip()[:500]
    return await _ask_niche(update, context)


async def skip_project_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _draft(context)["description"] = ""
    return await _ask_niche(update.callback_query, context)


async def _ask_niche(target, context):
    msg = (
        "Шаг 3/4: <b>Ниша / рынок</b>:\n"
        "<i>Например: women wellness, CRM tools, AI agents, Montenegro relocation</i>"
    )
    kb = cancel_button()
    if hasattr(target, "message"):
        await target.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    else:
        await target.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    return CP_NICHE


# ── Step 3: Niche ──────────────────────────────────────────────────────────────

async def handle_project_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _draft(context)["niche"] = update.message.text.strip()[:200]
    await update.message.reply_text(
        "Шаг 4/4: <b>Язык</b> итогового анализа и отчётов:",
        parse_mode="HTML",
        reply_markup=language_choice(),
    )
    return CP_LANG


# ── Step 4: Language ───────────────────────────────────────────────────────────

async def handle_project_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":")[1]   # lang:ru → ru
    draft = _draft(context)
    draft["output_language"] = lang

    # Show confirmation
    summary = (
        f"<b>Подтвердите создание проекта:</b>\n\n"
        f"📁 <b>Название:</b> {draft['name']}\n"
        f"📝 <b>Описание:</b> {draft.get('description') or '—'}\n"
        f"🎯 <b>Ниша:</b> {draft.get('niche') or '—'}\n"
        f"🌐 <b>Язык анализа:</b> {lang.upper()}\n"
    )
    await query.edit_message_text(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Создать",  callback_data="proj_confirm:yes"),
            InlineKeyboardButton("❌ Отмена",   callback_data="cancel_conv"),
        ]]),
    )
    return CP_CONFIRM


# ── Step 5: Confirm ────────────────────────────────────────────────────────────

async def handle_project_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    draft = _draft(context)
    uid = get_uid(update)

    project_id = _make_project_id(draft["name"])
    project = Project(
        id=project_id,
        owner_telegram_id=uid,
        name=draft["name"],
        description=draft.get("description", ""),
        niche=draft.get("niche", ""),
        output_language=draft.get("output_language", "en"),
        enabled=True,
        archived=False,
    )
    db.create_project(project)
    _clear(context)
    logger.info(f"Project created: {project_id} by user {uid}")

    await query.edit_message_text(
        f"✅ <b>Проект создан!</b>\n\n"
        f"📁 <b>{project.name}</b>\n"
        f"🆔 ID: <code>{project_id}</code>\n"
        f"🎯 Ниша: {project.niche or '—'}\n"
        f"🌐 Язык: {project.output_language.upper()}",
        parse_mode="HTML",
        reply_markup=after_project_created(project_id),
    )
    return ConversationHandler.END


# ── Cancel ─────────────────────────────────────────────────────────────────────

async def cancel_create_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _clear(context)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Создание проекта отменено.")
    elif update.message:
        await update.message.reply_text("❌ Создание проекта отменено.")
    return ConversationHandler.END


# ── ConversationHandler factory ────────────────────────────────────────────────

def build_create_project_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("create_project", start_create_project)],
        states={
            CP_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_project_name)],
            CP_DESC:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_project_desc),
                CallbackQueryHandler(skip_project_desc, pattern="^skip$"),
            ],
            CP_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_project_niche)],
            CP_LANG:  [CallbackQueryHandler(handle_project_lang, pattern="^lang:")],
            CP_CONFIRM: [CallbackQueryHandler(handle_project_confirm, pattern="^proj_confirm:")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_create_project),
            CallbackQueryHandler(cancel_create_project, pattern="^cancel_conv$"),
        ],
        allow_reentry=True,
        name="create_project",
        persistent=False,
    )
