"""
APScheduler-based scheduler.
Reads monitors.yaml, schedules each enabled monitor by cron.
Prevents concurrent runs of the same monitor.
"""
import time
from loguru import logger

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

from config_loader import sync_to_db, get_all_monitors
from monitor_runner import run_monitor


def _make_job(monitor_id: str):
    def job():
        logger.info(f"[Scheduler] Triggered monitor: {monitor_id}")
        run_monitor(monitor_id)
    job.__name__ = f"job_{monitor_id}"
    return job


def start_scheduler() -> None:
    if not APSCHEDULER_AVAILABLE:
        logger.error("APScheduler not installed. Run: pip install apscheduler pytz")
        return

    sync_to_db()
    monitors = get_all_monitors(enabled_only=True)

    if not monitors:
        logger.warning("No enabled monitors found in monitors.yaml")
        return

    scheduler = BlockingScheduler(timezone="UTC")

    for monitor in monitors:
        if not monitor.schedule_cron:
            logger.debug(f"Monitor '{monitor.id}' has no cron schedule, skipping")
            continue

        try:
            tz = pytz.timezone(monitor.timezone)
        except Exception:
            logger.warning(f"Invalid timezone '{monitor.timezone}' for monitor '{monitor.id}', using UTC")
            tz = pytz.UTC

        # Parse cron parts — APScheduler uses positional: minute hour day month day_of_week
        cron_parts = monitor.schedule_cron.strip().split()
        if len(cron_parts) != 5:
            logger.warning(f"Invalid cron '{monitor.schedule_cron}' for monitor '{monitor.id}'")
            continue

        minute, hour, day, month, day_of_week = cron_parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day,
            month=month, day_of_week=day_of_week,
            timezone=tz,
        )

        scheduler.add_job(
            _make_job(monitor.id),
            trigger=trigger,
            id=monitor.id,
            name=monitor.name,
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info(f"  Scheduled: {monitor.name} [{monitor.schedule_cron} {monitor.timezone}]")

    logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
