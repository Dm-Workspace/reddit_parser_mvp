from fastapi import APIRouter

router = APIRouter()

RUN_MODE_LABELS = {
    "hot_last_7d":  {"label": "Горячие обсуждения за 7 дней",    "description": "Подходит для регулярного мониторинга актуальных болей и тем."},
    "rising_24h":   {"label": "Быстро растущие темы за 24 часа", "description": "Подходит для раннего обнаружения новых трендов."},
    "top_week":     {"label": "Лучшее за неделю",                 "description": "Показывает самые заметные обсуждения недели."},
    "top_month":    {"label": "Лучшее за месяц",                  "description": "Подходит для стратегического анализа устойчивых тем."},
}

SCHEDULE_LABELS = {
    "manual":    {"label": "Только ручной запуск",  "description": "Монитор запускается только когда вы нажимаете «Запустить»."},
    "weekly":    {"label": "1 раз в неделю",         "description": ""},
    "biweekly":  {"label": "1 раз в 2 недели",       "description": ""},
    "monthly":   {"label": "1 раз в месяц",          "description": ""},
    "disabled":  {"label": "Отключено",              "description": "Автоматические запуски отключены."},
}

STATUS_LABELS = {
    "running":                  {"label": "Выполняется",                  "color": "blue"},
    "completed":                {"label": "Завершён",                     "color": "green"},
    "completed_with_warning":   {"label": "Завершён с предупреждением",   "color": "yellow"},
    "failed":                   {"label": "Ошибка",                       "color": "red"},
    "queued":                   {"label": "В очереди",                    "color": "gray"},
}

SOURCE_LABELS = {
    "reddit":   {"label": "Reddit",   "status": "active",      "icon": "🟠"},
    "youtube":  {"label": "YouTube",  "status": "coming_soon", "icon": "🔴"},
}

STORAGE_PROVIDER_LABELS = {
    "local":            "Локально",
    "google_drive":     "Google Drive",
    "s3":               "Amazon S3",
    "r2":               "Cloudflare R2",
    "railway_bucket":   "Railway Storage",
}


@router.get("/labels")
async def get_labels():
    """Return all i18n label mappings for the Mini App."""
    return {
        "run_modes":         RUN_MODE_LABELS,
        "schedules":         SCHEDULE_LABELS,
        "statuses":          STATUS_LABELS,
        "sources":           SOURCE_LABELS,
        "storage_providers": STORAGE_PROVIDER_LABELS,
    }
