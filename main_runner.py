#!/usr/bin/env python3
"""
Railway Cron Runner — technical scheduler only.

Usage:
  python main_runner.py --run-due-monitors    # run monitors with next_run_at <= NOW()
  python main_runner.py --run-queued          # execute bot-queued runs
  python main_runner.py --run-monitor <id>    # force-run specific monitor

Railway cron (railway.json): runs every 30 minutes.
Only monitors with schedule_mode=scheduled are touched automatically.
All new monitors default to schedule_mode=manual — not touched by cron.
"""
import argparse
import sys

from loguru import logger


def _setup():
    from utils.logger import setup_logger
    setup_logger("INFO")
    from storage import database as db
    db.init_db()
    from config_loader import seed_system_presets, sync_monitors_yaml
    seed_system_presets()
    sync_monitors_yaml()


# ── Due monitors ───────────────────────────────────────────────────────────────

def run_due_monitors() -> None:
    """
    Run all monitors WHERE schedule_mode='scheduled' AND next_run_at <= NOW().
    Skips monitors that already have an active run.
    """
    from storage import database as db
    from monitor_runner import run_monitor

    due = db.get_due_monitors()  # checks schedule_mode=scheduled AND next_run_at <= NOW
    if not due:
        logger.info("No due monitors.")
        return

    logger.info(f"Due monitors: {len(due)}")
    ran = 0
    for monitor in due:
        if not monitor.enabled or monitor.archived:
            logger.debug(f"[skip] {monitor.id} — disabled/archived")
            continue
        active = db.get_active_run_for_monitor(monitor.id)
        if active:
            logger.warning(f"[skip] {monitor.id} — already running ({active.id})")
            continue
        logger.info(f"[due]  {monitor.id} ({monitor.name}) — starting")
        try:
            run = run_monitor(monitor.id)
            if run:
                logger.success(f"  ✓ {monitor.id} → {run.status} ({run.total_posts}p/{run.total_comments}c)")
                ran += 1
            else:
                logger.error(f"  ✗ {monitor.id} → run returned None")
        except Exception as e:
            logger.error(f"  ✗ {monitor.id} failed: {e}")

    logger.info(f"run-due-monitors: {ran}/{len(due)} ran")


# ── Queued runs ────────────────────────────────────────────────────────────────

def run_queued() -> None:
    """
    Pick up run records with status=queued (created by Telegram bot)
    and execute them via monitor_runner.
    """
    from storage import database as db
    from storage.models import RUN_QUEUED
    from monitor_runner import run_monitor

    queued = db.list_runs_by_status(RUN_QUEUED)
    if not queued:
        logger.debug("No queued runs.")
        return

    logger.info(f"Queued runs: {len(queued)}")
    for run in queued:
        monitor = db.get_monitor(run.monitor_id)
        if not monitor:
            logger.warning(f"[skip queued] run {run.id}: monitor {run.monitor_id} not found")
            continue
        if not monitor.enabled or monitor.archived:
            logger.warning(f"[skip queued] run {run.id}: monitor disabled/archived")
            continue
        active = db.get_active_run_for_monitor(run.monitor_id)
        if active and active.id != run.id:
            logger.warning(f"[skip queued] run {run.id}: monitor already running ({active.id})")
            continue
        logger.info(f"[queued] Executing run {run.id} for monitor {run.monitor_id}")
        try:
            result = run_monitor(run.monitor_id, existing_run_id=run.id)
            if result:
                logger.success(f"  ✓ run {run.id} → [{result.status}]")
        except Exception as e:
            logger.error(f"  ✗ run {run.id} failed: {e}")


# ── Single monitor (force) ─────────────────────────────────────────────────────

def run_single_monitor(monitor_id: str) -> None:
    from monitor_runner import run_monitor
    logger.info(f"[force] Running monitor: {monitor_id}")
    run = run_monitor(monitor_id)
    if run:
        logger.success(f"  ✓ {monitor_id} → run {run.id} [{run.status}]")
    else:
        logger.error(f"  ✗ {monitor_id} → run returned None")


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main_runner.py",
        description="Reddit Parser — Railway Cron Runner",
    )
    parser.add_argument("--verbose",          action="store_true")
    parser.add_argument("--run-due-monitors", action="store_true",
                        help="Run monitors with schedule_mode=scheduled and next_run_at <= NOW")
    parser.add_argument("--run-queued",       action="store_true",
                        help="Execute bot-queued runs (status=queued)")
    parser.add_argument("--run-monitor",      metavar="MONITOR_ID",
                        help="Force-run a specific monitor by ID")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not (args.run_due_monitors or args.run_queued or args.run_monitor):
        parser.print_help()
        sys.exit(0)

    _setup()

    # Queued runs first (highest priority — user-initiated via bot)
    if args.run_queued or args.run_due_monitors:
        run_queued()

    if args.run_due_monitors:
        run_due_monitors()

    if args.run_monitor:
        run_single_monitor(args.run_monitor)


if __name__ == "__main__":
    main()
