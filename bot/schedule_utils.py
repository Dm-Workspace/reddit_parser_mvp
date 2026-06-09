"""
Schedule utilities: cron building, next_run_at computation.
"""
import re
from datetime import datetime, timedelta
from typing import Optional

import pytz

_WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_WEEKDAY_CRON  = [1, 2, 3, 4, 5, 6, 0]   # croniter: Mon=1…Sun=0


def build_weekly_cron(weekday: int, hour: int, minute: int) -> str:
    """weekday: 0=Mon … 6=Sun. Returns cron like '0 8 * * 1' (Mon 08:00)."""
    cron_day = _WEEKDAY_CRON[weekday % 7]
    return f"{minute} {hour} * * {cron_day}"


def build_monthly_cron(day: int, hour: int, minute: int) -> str:
    """day: 1-28. Returns cron like '0 8 1 * *' (1st of month at 08:00)."""
    return f"{minute} {hour} {day} * *"


def parse_time(time_str: str) -> tuple:
    """Parse 'HH:MM' → (hour, minute). Raises ValueError if invalid."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", time_str.strip())
    if not m:
        raise ValueError(f"Неверный формат времени. Введите HH:MM, например 08:00")
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Время за пределами допустимого диапазона (00:00–23:59)")
    return hour, minute


def compute_next_run_at(
    frequency: str,
    schedule_cron: str,
    timezone_str: str,
    from_dt: datetime = None,
) -> Optional[str]:
    """
    Compute the next run datetime string (ISO format) based on frequency.
    Returns None for manual/disabled.
    """
    if frequency in ("none", "manual", "disabled", ""):
        return None
    try:
        from croniter import croniter
        tz = pytz.timezone(timezone_str)
    except Exception:
        return None

    if from_dt is None:
        from_dt = datetime.now(tz)
    elif from_dt.tzinfo is None:
        from_dt = tz.localize(from_dt)

    if frequency == "biweekly":
        # biweekly: next run = from_dt + 14 days at 08:00
        next_dt = from_dt + timedelta(days=14)
        next_dt = next_dt.replace(hour=8, minute=0, second=0, microsecond=0)
        return next_dt.strftime("%Y-%m-%d %H:%M:%S")

    if not schedule_cron:
        return None

    try:
        # Make from_dt naive in local tz for croniter
        local_naive = from_dt.astimezone(tz).replace(tzinfo=None)
        cron = croniter(schedule_cron, local_naive)
        next_local = cron.get_next(datetime)
        next_aware = tz.localize(next_local)
        return next_aware.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def frequency_label(frequency: str, schedule_cron: str = "") -> str:
    labels = {
        "none":     "👆 Только вручную",
        "manual":   "👆 Только вручную",
        "weekly":   "📅 Раз в неделю",
        "biweekly": "📅 Раз в 2 недели",
        "monthly":  "📅 Раз в месяц",
        "disabled": "🚫 Отключён",
        "custom_cron": f"⚙️ Cron: {schedule_cron}",
    }
    return labels.get(frequency, frequency)


def days_since_run(last_run_at: Optional[str]) -> Optional[int]:
    """Return number of days since last_run_at, or None if never ran."""
    if not last_run_at:
        return None
    try:
        last = datetime.fromisoformat(last_run_at.replace("Z", "").replace(" ", "T"))
        now = datetime.utcnow()
        return max(0, (now - last).days)
    except Exception:
        return None
