#!/usr/bin/env python3
"""
Railway Cron Runner — technical scheduler + admin CLI.

Runtime modes (Railway cron):
  --run-due-monitors   Run monitors where schedule_mode=scheduled AND next_run_at<=NOW
  --run-queued         Execute runs queued by Telegram bot (status=queued)

Single-monitor mode:
  --run-monitor <id>   Force-run a specific monitor by ID

Admin / debug commands (run locally or on Railway shell):
  --db-check           Show DB connection status and table counts
  --init-db            Create tables + seed system presets (idempotent)
  --list-runs          Show last 10 runs
  --list-projects      Show all projects (active + archived)
  --list-monitors      Show all monitors (active + archived)

Railway cron schedule (recommended):  0 */6 * * *  (every 6 hours)

IMPORTANT — cron policy:
  - Only monitors with schedule_mode=scheduled are touched
  - All new monitors default to schedule_mode=manual — cron never touches them
  - Scheduled monitors run only when next_run_at <= NOW
"""
import argparse
import os
import sys

# ── Load .env before any os.environ reads or lazy module imports ──────────────
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass   # Railway injects ENV directly — dotenv not required

from loguru import logger


def _setup(verbose: bool = False) -> None:
    from utils.logger import setup_logger
    setup_logger("DEBUG" if verbose else "INFO")
    from storage import database as db
    db.init_db()
    from config_loader import seed_system_presets, sync_monitors_yaml
    seed_system_presets()
    sync_monitors_yaml()


# ── Admin / debug commands ────────────────────────────────────────────────────

def cmd_db_check() -> None:
    """Print DB connection status and table counts."""
    from utils.logger import setup_logger
    setup_logger("WARNING")   # suppress noise for clean output
    from storage import database as db

    info = db.get_db_info()
    print()
    print("=" * 50)
    print("  DB Health Check")
    print("=" * 50)

    url_set = info["db_url_set"]
    db_type = info["db_type"]
    print(f"  DATABASE_URL set : {'YES' if url_set else 'NO (SQLite fallback)'}")
    print(f"  Database type    : {db_type}")

    if info["connected"]:
        print(f"  Connection       : OK")
        print()
        print("  Table counts:")
        for tbl, cnt in info["counts"].items():
            print(f"    {tbl:<25} {cnt}")
    else:
        print(f"  Connection       : ERROR")
        print(f"  Error            : {info['error']}")

    print("=" * 50)
    print()
    if not info["connected"]:
        sys.exit(1)


def cmd_init_db() -> None:
    """Create tables and seed system presets. Idempotent — safe to run multiple times."""
    from utils.logger import setup_logger
    setup_logger("INFO")
    from storage import database as db
    from config_loader import seed_system_presets, sync_monitors_yaml

    print("Initialising database...")
    db.init_db()
    print("  [ok] Tables created / verified")

    seed_system_presets()
    print("  [ok] System presets seeded")

    sync_monitors_yaml()
    print("  [ok] monitors.yaml synced (if exists)")

    info = db.get_db_info()
    print(f"\nDB type: {info['db_type']}")
    for tbl, cnt in info["counts"].items():
        print(f"  {tbl:<25} {cnt} rows")
    print("\nDone.")


def cmd_list_runs(limit: int = 10) -> None:
    from utils.logger import setup_logger
    setup_logger("WARNING")
    from storage import database as db
    db.init_db()

    runs = db.list_runs(limit=limit)
    if not runs:
        print("No runs found.")
        return

    print()
    header = f"{'run_id':<14} {'project_id':<20} {'monitor_id':<22} {'status':<22} {'posts':>6} {'comments':>9} {'started_at'}"
    print(header)
    print("-" * len(header))
    for r in runs:
        print(
            f"{r.id:<14} {r.project_id:<20} {r.monitor_id:<22} "
            f"{r.status:<22} {r.total_posts:>6} {r.total_comments:>9} "
            f"{(r.started_at or '')[:16]}"
        )
    print()


def cmd_list_projects() -> None:
    from utils.logger import setup_logger
    setup_logger("WARNING")
    from storage import database as db
    db.init_db()

    projects = db.list_projects(include_archived=True)
    if not projects:
        print("No projects found.")
        return

    print()
    header = f"{'id':<30} {'name':<25} {'owner':<12} {'lang':<5} {'archived'}"
    print(header)
    print("-" * len(header))
    for p in projects:
        arch = "ARCHIVED" if p.archived else "active"
        print(f"{p.id:<30} {p.name:<25} {p.owner_telegram_id:<12} {p.output_language:<5} {arch}")
    print()


def cmd_list_monitors() -> None:
    from utils.logger import setup_logger
    setup_logger("WARNING")
    from storage import database as db
    db.init_db()

    monitors = db.list_monitors(include_archived=True)
    if not monitors:
        print("No monitors found.")
        return

    print()
    header = f"{'id':<28} {'project_id':<20} {'schedule_mode':<12} {'frequency':<10} {'archived'}"
    print(header)
    print("-" * len(header))
    for m in monitors:
        arch = "ARCHIVED" if m.archived else "active"
        print(f"{m.id:<28} {m.project_id:<20} {m.schedule_mode:<12} {m.frequency:<10} {arch}")
    print()


# ── Due monitors (Railway cron) ───────────────────────────────────────────────

def run_due_monitors() -> None:
    """
    Run all monitors WHERE schedule_mode='scheduled' AND next_run_at <= NOW().
    Skips monitors that already have an active run.
    Does NOT touch manual monitors.
    """
    from storage import database as db
    from monitor_runner import run_monitor

    due = db.get_due_monitors()
    if not due:
        logger.info("No due monitors.")
        return

    logger.info(f"Due monitors: {len(due)}")
    ran = 0
    for monitor in due:
        if not monitor.enabled or monitor.archived:
            logger.debug(f"[skip] {monitor.id} — disabled/archived")
            continue

        # Respect min_days_between_runs even for scheduled mode
        from bot.schedule_utils import days_since_run
        days = days_since_run(monitor.last_run_at)
        if days is not None and days < monitor.min_days_between_runs:
            logger.warning(
                f"[skip] {monitor.id} — ran {days}d ago, min={monitor.min_days_between_runs}d"
            )
            continue

        active = db.get_active_run_for_monitor(monitor.id)
        if active:
            logger.warning(f"[skip] {monitor.id} — already running ({active.id})")
            continue

        logger.info(f"[due]  {monitor.id} ({monitor.name})")
        try:
            run = run_monitor(monitor.id)
            if run:
                logger.success(
                    f"  ✓ {monitor.id} → {run.status} "
                    f"({run.total_posts}p/{run.total_comments}c)"
                )
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
        logger.info(f"[queued] {run.id} → monitor {run.monitor_id}")
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

# ── Parser QA / Smoke test commands ──────────────────────────────────────────

def cmd_reddit_check() -> None:
    """
    Connectivity check for the configured Reddit backend.
    playwright mode: launches browser, fetches 3 posts from r/Supplements.
    requests_json mode: HTTP GET to .json endpoint, shows status code.
    oauth mode: PRAW connectivity (no raw HTTP info).
    """
    from utils.logger import setup_logger
    setup_logger("WARNING")

    from reddit_client import (
        create_reddit_client, close_reddit_client,
        REDDIT_ACCESS_MODE, REDDIT_USER_AGENT,
        REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
        get_effective_mode, _playwright_available,
    )

    effective = get_effective_mode()
    ua_set    = bool(REDDIT_USER_AGENT)
    creds_set = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)
    pw_pkg    = _playwright_available()

    print()
    print("=" * 62)
    print("  Reddit Access Check")
    print("=" * 62)
    print(f"  REDDIT_ACCESS_MODE   : {REDDIT_ACCESS_MODE}")
    print(f"  selected_client      : {effective}")
    print(f"  user_agent_detected  : {'YES — ' + REDDIT_USER_AGENT if ua_set else 'NO (using default)'}")
    print(f"  credentials_detected : {'YES' if creds_set else 'NO (not needed for playwright/requests_json)'}")
    print(f"  playwright_available : {'YES' if pw_pkg else 'NO — run: pip install playwright && playwright install chromium'}")
    print(f"  test_subreddit       : Supplements")
    print()

    if effective == "playwright" and not pw_pkg:
        print("  browser_launch       : FAIL — playwright package not installed")
        print("  test_result          : FAIL")
        print("=" * 62)
        sys.exit(1)

    client = None
    try:
        if effective == "playwright":
            print("  browser_launch       : launching...")

        client = create_reddit_client()
        info   = client.test_connection("Supplements")

        pw_ok      = info.get("playwright_available", False)
        bl_status  = info.get("browser_launch", "n/a")
        http_st    = info.get("http_status")
        count      = info.get("children_count", 0)
        titles     = info.get("sample_titles", [])
        err        = info.get("error")

        if effective == "playwright":
            print(f"  browser_launch       : {bl_status}")
        else:
            print(f"  test_url             : {info.get('test_url', 'n/a')}")
            print(f"  http_status          : {http_st if http_st is not None else 'n/a'}")

        print(f"  raw_posts_fetched    : {count if count is not None else 'n/a'}")

        if err:
            print(f"  test_result          : FAIL")
            print(f"  error                : {err}")
            if effective == "requests_json" and http_st in (403, 429):
                print()
                print(f"  Hint: HTTP {http_st} — Reddit is blocking this IP/User-Agent.")
                print(f"        Switch to REDDIT_ACCESS_MODE=playwright for reliable access.")
            elif effective == "playwright":
                print()
                print(f"  Hint: Browser opened but no posts extracted.")
                print(f"        Reddit may have changed old.reddit.com layout.")
            sys.exit(1)

        print(f"  test_result          : ok")

        if titles:
            print()
            print(f"  sample_titles ({len(titles)}):")
            for i, t in enumerate(titles[:3], 1):
                print(f"    {i}. {t}")

    except Exception as e:
        print(f"  browser_launch       : error" if effective == "playwright" else "")
        print(f"  test_result          : FAIL")
        print(f"  error_message        : {e}")
        print("=" * 62)
        sys.exit(1)
    finally:
        if client:
            try:
                close_reddit_client(client)
            except Exception:
                pass

    print("=" * 62)
    print()


def cmd_parser_smoke_test(upload_drive: bool = False) -> None:
    """
    Run a live Reddit parse WITHOUT keyword filter.
    Goal: confirm the client fetches real posts and comments.
    0 posts → FAIL. Does not require REDDIT_CLIENT_ID/SECRET.
    """
    from utils.logger import setup_logger
    setup_logger("WARNING")
    from parser_qa import run_smoke_test, print_smoke_result

    print("Running parser smoke test (subreddits: Supplements, Biohackers, keywords: none)...")
    try:
        result = run_smoke_test(upload_drive=upload_drive)
    except RuntimeError as e:
        print(f"\n[ERROR] {e}\n")
        sys.exit(1)
    print_smoke_result(result)
    if result.status == "FAIL":
        sys.exit(1)


def cmd_parser_keyword_test() -> None:
    """
    Run a wider Reddit parse WITH keyword filter (magnesium/sleep/fatigue).
    Uses limit=50 per subreddit. 0 raw posts → FAIL. 0 matches → WARNING.
    Does not require REDDIT_CLIENT_ID/SECRET in public_json mode.
    """
    from utils.logger import setup_logger
    setup_logger("WARNING")
    from parser_qa import run_keyword_test, print_smoke_result

    print("Running keyword test (subreddits: Supplements, Biohackers, keywords: magnesium/sleep/fatigue)...")
    try:
        result = run_keyword_test()
    except RuntimeError as e:
        print(f"\n[ERROR] {e}\n")
        sys.exit(1)
    print_smoke_result(result)
    if result.status == "FAIL":
        sys.exit(1)


def cmd_parser_qa_file(xlsx_path: str) -> None:
    """
    Inspect a finished export Excel file and print a QA report.
    No network calls, no DB writes.
    """
    from utils.logger import setup_logger
    setup_logger("WARNING")
    from parser_qa import run_qa_file, print_qa_result, QA_FAIL

    print(f"Running QA on: {xlsx_path}")
    qa = run_qa_file(xlsx_path)
    print_qa_result(qa)
    if qa.status == QA_FAIL:
        sys.exit(1)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main_runner.py",
        description="Reddit Parser — Railway Cron Runner + Admin CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Railway cron mode (run every 6h):
  python main_runner.py --run-due-monitors --run-queued

Admin / debug:
  python main_runner.py --db-check
  python main_runner.py --init-db
  python main_runner.py --list-runs
  python main_runner.py --list-projects
  python main_runner.py --list-monitors
  python main_runner.py --run-monitor <monitor_id>

Reddit / Parser QA (no Telegram/Railway required):
  python main_runner.py --reddit-check
  python main_runner.py --parser-smoke-test
  python main_runner.py --parser-smoke-test --upload-drive
  python main_runner.py --parser-keyword-test
  python main_runner.py --parser-qa-file exports/smoke_test/.../smoke_*.xlsx
        """,
    )
    parser.add_argument("--verbose",          action="store_true", help="Debug logging")

    # Cron runtime
    parser.add_argument("--run-due-monitors", action="store_true",
                        help="Run scheduled monitors whose next_run_at <= NOW")
    parser.add_argument("--run-queued",       action="store_true",
                        help="Execute bot-queued runs (status=queued)")
    parser.add_argument("--run-monitor",      metavar="MONITOR_ID",
                        help="Force-run a specific monitor")

    # Admin / debug
    parser.add_argument("--db-check",         action="store_true",
                        help="Check DB connection and table counts")
    parser.add_argument("--init-db",          action="store_true",
                        help="Create tables and seed system presets")
    parser.add_argument("--list-runs",        action="store_true",
                        help="Show last 10 runs")
    parser.add_argument("--list-projects",    action="store_true",
                        help="Show all projects")
    parser.add_argument("--list-monitors",    action="store_true",
                        help="Show all monitors")

    # Reddit check
    parser.add_argument("--reddit-check",      action="store_true",
                        help="Test Reddit client connectivity (no OAuth needed in public_json mode)")

    # Parser QA
    parser.add_argument("--parser-smoke-test",   action="store_true",
                        help="Live smoke test — no keyword filter, checks raw collection")
    parser.add_argument("--upload-drive",        action="store_true",
                        help="With --parser-smoke-test: also upload exports to Drive")
    parser.add_argument("--parser-keyword-test", action="store_true",
                        help="Live keyword test (magnesium/sleep/fatigue, limit=50)")
    parser.add_argument("--parser-qa-file",      metavar="XLSX_PATH",
                        help="QA check an existing export Excel file")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    any_action = any([
        args.run_due_monitors, args.run_queued, args.run_monitor,
        args.db_check, args.init_db,
        args.list_runs, args.list_projects, args.list_monitors,
        args.reddit_check, args.parser_smoke_test,
        args.parser_keyword_test, args.parser_qa_file,
    ])
    if not any_action:
        parser.print_help()
        sys.exit(0)

    # ── Pure-diagnostic / QA commands (no full _setup needed) ─────────────────
    if args.db_check:
        cmd_db_check()
        return

    if args.init_db:
        cmd_init_db()
        return

    if args.list_runs:
        cmd_list_runs()
        return

    if args.list_projects:
        cmd_list_projects()
        return

    if args.list_monitors:
        cmd_list_monitors()
        return

    if args.reddit_check:
        cmd_reddit_check()
        return

    if args.parser_smoke_test:
        cmd_parser_smoke_test(upload_drive=args.upload_drive)
        return

    if args.parser_keyword_test:
        cmd_parser_keyword_test()
        return

    if args.parser_qa_file:
        cmd_parser_qa_file(args.parser_qa_file)
        return

    # ── Runtime modes — need full setup ───────────────────────────────────────
    _setup(verbose=args.verbose)

    # Queued runs first (user-initiated — highest priority)
    if args.run_queued or args.run_due_monitors:
        run_queued()

    if args.run_due_monitors:
        run_due_monitors()

    if args.run_monitor:
        run_single_monitor(args.run_monitor)


if __name__ == "__main__":
    main()
