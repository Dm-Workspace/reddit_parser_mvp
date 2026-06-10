"""
InlineKeyboard builders for the Telegram bot.
callback_data convention:
  {namespace}:{action}:{id}
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List


# ── Main menu ──────────────────────────────────────────────────────────────────

def main_menu() -> InlineKeyboardMarkup:
    import os
    from telegram import WebAppInfo
    miniapp_url = os.environ.get("MINIAPP_URL", "")
    rows = []
    if miniapp_url:
        rows.append([InlineKeyboardButton("🚀 Открыть Trend Hub", web_app=WebAppInfo(url=miniapp_url))])
    rows += [
        [InlineKeyboardButton("📁 Мои проекты",    callback_data="menu:projects")],
        [InlineKeyboardButton("➕ Создать проект", callback_data="menu:create_project")],
        [InlineKeyboardButton("📊 Запуски",        callback_data="menu:runs"),
         InlineKeyboardButton("🔧 Статус",         callback_data="menu:status")],
    ]
    return InlineKeyboardMarkup(rows)


# ── Project keyboards ──────────────────────────────────────────────────────────

def project_list(projects) -> InlineKeyboardMarkup:
    rows = []
    for p in projects:
        rows.append([InlineKeyboardButton(
            f"📁 {p.name}", callback_data=f"proj:open:{p.id}"
        )])
    rows.append([InlineKeyboardButton("➕ Новый проект", callback_data="menu:create_project")])
    return InlineKeyboardMarkup(rows)


def project_menu(project_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Мониторы",        callback_data=f"proj:monitors:{project_id}")],
        [InlineKeyboardButton("➕ Создать монитор", callback_data=f"proj:create_monitor:{project_id}")],
        [InlineKeyboardButton("⚙️ Изменить",        callback_data=f"proj:edit:{project_id}"),
         InlineKeyboardButton("🗄 Архив",           callback_data=f"proj:archive:{project_id}")],
        [InlineKeyboardButton("◀️ Назад",           callback_data="menu:projects")],
    ])


def after_project_created(project_id: str) -> InlineKeyboardMarkup:
    """Shown after a project is successfully created."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Создать монитор",    callback_data=f"proj:create_monitor:{project_id}")],
        [InlineKeyboardButton("📊 Мониторы проекта",  callback_data=f"proj:monitors:{project_id}"),
         InlineKeyboardButton("⚙️ Настройки",         callback_data=f"proj:open:{project_id}")],
        [InlineKeyboardButton("📁 Мои проекты",       callback_data="menu:projects")],
        [InlineKeyboardButton("🏠 Главное меню",      callback_data="menu:main")],
    ])


def after_monitor_created(monitor_id: str, project_id: str) -> InlineKeyboardMarkup:
    """Shown after a monitor is successfully created."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Запустить сейчас", callback_data=f"run_start:{monitor_id}")],
        [InlineKeyboardButton("📊 Открыть монитор",  callback_data=f"mon:open:{monitor_id}"),
         InlineKeyboardButton("🕒 Расписание",       callback_data=f"mon:schedule:{monitor_id}")],
        [InlineKeyboardButton("📁 К проекту",        callback_data=f"proj:open:{project_id}")],
        [InlineKeyboardButton("🏠 Главное меню",     callback_data="menu:main")],
    ])


def retry_project_id() -> InlineKeyboardMarkup:
    """Shown when user enters invalid project_id."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Мои проекты",     callback_data="menu:projects")],
        [InlineKeyboardButton("🔁 Ввести снова",    callback_data="mon:retry_pid")],
        [InlineKeyboardButton("🏠 Главное меню",    callback_data="menu:main")],
    ])


def confirm_archive(entity: str, entity_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Архивировать", callback_data=f"confirm_archive:{entity}:{entity_id}"),
        InlineKeyboardButton("❌ Отмена",       callback_data="cancel_action"),
    ]])


# ── Monitor keyboards ──────────────────────────────────────────────────────────

def monitor_list(monitors, project_id: str) -> InlineKeyboardMarkup:
    rows = []
    for m in monitors:
        icon = "🟢" if m.enabled and not m.archived else "🔴"
        rows.append([InlineKeyboardButton(
            f"{icon} {m.name}", callback_data=f"mon:open:{m.id}"
        )])
    rows.append([InlineKeyboardButton("➕ Новый монитор", callback_data=f"proj:create_monitor:{project_id}")])
    rows.append([InlineKeyboardButton("◀️ Назад",        callback_data=f"proj:open:{project_id}")])
    return InlineKeyboardMarkup(rows)


def monitor_menu(monitor_id: str, project_id: str = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("▶️ Запустить",        callback_data=f"mon:run:{monitor_id}")],
        [InlineKeyboardButton("🕒 Расписание",       callback_data=f"mon:schedule:{monitor_id}"),
         InlineKeyboardButton("⚙️ Изменить",         callback_data=f"mon:edit:{monitor_id}")],
        [InlineKeyboardButton("📊 История запусков", callback_data=f"mon:runs:{monitor_id}"),
         InlineKeyboardButton("🗄 Архив",            callback_data=f"mon:archive:{monitor_id}")],
    ]
    if project_id:
        rows.append([InlineKeyboardButton("◀️ К проекту", callback_data=f"proj:open:{project_id}")])
    rows.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def run_confirm_keyboard(monitor_id: str, force: bool = False) -> InlineKeyboardMarkup:
    cb = f"run_force:{monitor_id}" if force else f"run_start:{monitor_id}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ Запустить", callback_data=cb),
        InlineKeyboardButton("❌ Отмена",    callback_data="cancel_action"),
    ]])


# ── Schedule keyboards ─────────────────────────────────────────────────────────

def monitor_schedule_choice() -> InlineKeyboardMarkup:
    """
    Used during /create_monitor flow (step 6).
    Distinct from schedule_frequency() which is used when editing an existing monitor.
    'Только вручную' creates the monitor immediately (no extra confirm step).
    '⬅️ Назад' returns to run mode.
    '🛑 Отменить создание' asks for full-cancel confirmation.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Только вручную",          callback_data="mon_sch:manual")],
        [InlineKeyboardButton("🕒 1 раз в неделю",          callback_data="mon_sch:weekly")],
        [InlineKeyboardButton("🗓 1 раз в 2 недели",        callback_data="mon_sch:biweekly")],
        [InlineKeyboardButton("📅 1 раз в месяц",           callback_data="mon_sch:monthly")],
        [InlineKeyboardButton("⬅️ Назад (режим запуска)",   callback_data="mon_sch:back")],
        [InlineKeyboardButton("🛑 Отменить создание",       callback_data="mon_sch:cancel_full")],
    ])


def monitor_cancel_confirm() -> InlineKeyboardMarkup:
    """Shown when user asks to fully cancel monitor creation mid-flow."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Да, отменить",            callback_data="mon_cancel:confirm")],
        [InlineKeyboardButton("↩️ Нет, продолжить",         callback_data="mon_cancel:back")],
    ])


def schedule_frequency() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👆 Только вручную",  callback_data="sch:manual")],
        [InlineKeyboardButton("📅 Раз в неделю",    callback_data="sch:weekly")],
        [InlineKeyboardButton("📅 Раз в 2 недели",  callback_data="sch:biweekly")],
        [InlineKeyboardButton("📅 Раз в месяц",     callback_data="sch:monthly")],
        [InlineKeyboardButton("🚫 Отключить",       callback_data="sch:disabled")],
        [InlineKeyboardButton("❌ Отмена",          callback_data="cancel_action")],
    ])


def schedule_weekday() -> InlineKeyboardMarkup:
    days = [("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3), ("Пт", 4), ("Сб", 5), ("Вс", 6)]
    row = [InlineKeyboardButton(name, callback_data=f"sch_day:{num}") for name, num in days]
    return InlineKeyboardMarkup([row[:4], row[4:]])


def schedule_day_of_month() -> InlineKeyboardMarkup:
    rows = []
    days = list(range(1, 29))
    for i in range(0, len(days), 7):
        rows.append([InlineKeyboardButton(str(d), callback_data=f"sch_dom:{d}") for d in days[i:i+7]])
    return InlineKeyboardMarkup(rows)


# ── Conversation keyboards ─────────────────────────────────────────────────────

def language_choice() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 RU", callback_data="lang:ru"),
        InlineKeyboardButton("🇬🇧 EN", callback_data="lang:en"),
        InlineKeyboardButton("🇺🇦 UK", callback_data="lang:uk"),
    ]])


def yes_no(yes_cb: str, no_cb: str = "cancel_action") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да",     callback_data=yes_cb),
        InlineKeyboardButton("⏭ Позже",  callback_data=no_cb),
    ]])


def preset_list(presets, preset_type: str, allow_custom: bool = True) -> InlineKeyboardMarkup:
    """preset_type: 'sr' (subreddit) or 'kw' (keyword)"""
    rows = []
    for p in presets:
        icon = "🔧" if p.is_system else "👤"
        label = f"{icon} {p.name}"
        rows.append([InlineKeyboardButton(label, callback_data=f"{preset_type}_preset:{p.id}")])
    if allow_custom:
        rows.append([InlineKeyboardButton("✍️ Ввести вручную", callback_data=f"{preset_type}_preset:__custom__")])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_conv")])
    return InlineKeyboardMarkup(rows)


def run_mode_choice() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 hot_last_7d — горячее за 7 дн.",  callback_data="runmode:hot_last_7d")],
        [InlineKeyboardButton("📈 rising_24h — растущее 24 ч.",     callback_data="runmode:rising_24h")],
        [InlineKeyboardButton("⭐ top_week — топ за неделю",        callback_data="runmode:top_week")],
        [InlineKeyboardButton("🏆 top_month — топ за месяц",        callback_data="runmode:top_month")],
    ])


def cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_conv")
    ]])


def skip_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏭ Пропустить", callback_data="skip"),
        InlineKeyboardButton("❌ Отмена",     callback_data="cancel_conv"),
    ]])
