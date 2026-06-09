#!/usr/bin/env python3
"""
Cron Runner — CLI entry point for Railway scheduled jobs.

Usage:
  python main_runner.py --run-due-monitors    # check cron schedules, run due monitors
  python main_runner.py --run-monitor <id>    # run a specific monitor immediately
  python main_runner.py --run-queued          # run any queued runs from bot

Railway cron (railway.json):
  "*/30 * * * *" → runs every 30 minutes (UTC)
  Timezone-aware due-check is done inside this script.
"""
import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from utils.logger import setup_logger


# ── Cron due-check ─────────────────────────────────────────────────────────────

def _is_due(monitor, last_run) -> bool:
    """
    Return True if the monitor's cron schedule should fire now.
    Called from a Railway cron every 30 min — checks if the monitor
    was supposed to run since the last completed run.
    """
    if not monitor.schedule_cron:
        return False

    try:
        from croniter import croniter
        import pytz
    except ImportError:
        logger.error("croniter / pytz not installed. Run: pip install croniter pytz")
        return False

    try:
        tz = pytz.timezone(monitor.timezone)
    except Exception:
        tz = pytz.UTC

    now_local_naive = datetime.now(tz).replace(tzinfo=None)

    try:
        cron  = croniter(monitor.schedule_cron, now_local_naive)
        last_expected_naive = cron.get_prev(datetime)
    except Exception as e:
        logger.warning(f"Invalid cron '{monitor.schedule_cron}' for {monitor.id}: {e}")
        return False

    # Convert expected fire time to UTC for comparison
    last_expected_utc = tz.localize(last_expected_naive).astimezone(pytz.UTC)

    if last_run is None:
        # Never ran — due if expected fire was within last 35 min
        delta = datetime.now(pytz.UTC) - last_expected_utc
        return 0 <= delta.total_seconds() <= 35 * 60

    # Parse last run's started_at as UTC
    try:
        last_started_str = last_run.started_at.replace("Z", "").replace(" ", "T")
        last_started = datetime.fromisoformat(last_started_str)
        if last_started.tzinfo is None:
            last_started = pytz.UTC.localize(last_started)
    except Exception:
        return True

    return last_expected_utc > last_started


# ── Runner logic ───────────────────────────────────────────────────────────────

def run_due_monitors() -> None:
    """Check all enabled monitors and run those whose cron is due."""
    from config_loader import sync_to_db
    from storage import database as db

    sync_to_db()
    monitors = db.list_monitors(enabled_only=True)
    if not monitors:
        logger.warning("No enabled monitors found")
        return

    ran = 0
    for monitor in monitors:
        last_run = db.get_last_run_for_monitor(monitor.id)
        if not _is_due(monitor, last_run):
            logger.debug(f"[skip] {monitor.id} — not due yet")
            continue

        active = db.get_active_run_for_monitor(monitor.id)
        if active:
            logger.warning(f"[skip] {monitor.id} — already running ({active.id})")
            continue

        logger.info(f"[due]  {monitor.id} — starting run")
        _execute(monitor.id)
        ran += 1

    logger.info(f"run-due-monitors: {ran}/{len(monitors)} monitors ran")


def run_queued() -> None:
    """Pick up any runs with status='queued' (created by bot) and execute them."""
    from storage import database as db
    db.init_db()
    queued = db.get_queued_runs()
    if not queued:
        logger.debug("No queued runs")
        return

    logger.info(f"Found {len(queued)} queued run(s)")
    for run in queued:
        active = db.get_active_run_for_monitor(run.monitor_id)
        if active and active.id != run.id:
            logger.warning(f"[skip queued] {run.id} — monitor already running")
            continue

        logger.info(f"[queued] Executing run {run.id} for monitor {run.monitor_id}")
        from monitor_runner import run_monitor
        run_monitor(run.monitor_id, existing_run_id=run.id)


def _execute(monitor_id: str) -> None:
    from monitor_runner import run_monitor
    run = run_monitor(monitor_id)
    if run:
        logger.info(
            f"  ✓ {monitor_id} → {run.status} "
            f"({run.total_posts} posts, {run.total_comments} comments)"
        )
    else:
        logger.error(f"  ✗ {monitor_id} → run returned None")


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main_runner.py",
        description="Reddit Parser — Cron Runner (Railway)",
    )
    parser.add_argument("--verbose",           action="store_true")
    parser.add_argument("--run-due-monitors",  action="store_true",
                        help="Check cron schedules and run due monitors")
    parser.add_argument("--run-queued",        action="store_true",
                        help="Execute queued runs created by the Telegram bot")
    parser.add_argument("--run-monitor",       metavar="MONITOR_ID",
                        help="Run a specific monitor immediately")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    setup_logger("DEBUG" if args.verbose else "INFO")

    if not (args.run_due_monitors or args.run_queued or args.run_monitor):
        parser.print_help()
        sys.exit(0)

    # Always run queued first (created by bot), then check scheduled
    if args.run_queued or args.run_due_monitors:
        run_queued()

    if args.run_due_monitors:
        run_due_monitors()

    if args.run_monitor:
        from config_loader import sync_to_db
        sync_to_db()
        logger.info(f"Force-running monitor: {args.run_monitor}")
        _execute(args.run_monitor)


if __name__ == "__main__":
    main()
