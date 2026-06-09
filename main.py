#!/usr/bin/env python3
"""
Multi-Monitor Trend Intelligence System v5
CLI entry point.

Subcommands:
  parse          — direct parse (v4 mode, no DB)
  run-monitor    — run a single monitor from monitors.yaml
  run-all        — run all enabled monitors
  list-monitors  — show monitors from monitors.yaml
  list-runs      — show recent runs from DB
  scheduler      — start APScheduler daemon
"""
import argparse
import sys
import os

from loguru import logger
from utils.logger import setup_logger


# ─── Subcommand handlers ──────────────────────────────────────────────────────

def cmd_parse(args) -> None:
    """Legacy direct parse mode — no DB, no monitor config."""
    from config import (
        SUPPORTED_PERIODS, SUPPORTED_SORTS, SUPPORTED_EXPORTS,
        SUPPORTED_LANGUAGE_MODES, RUN_MODES, KEYWORD_PRESETS,
        SUBREDDIT_PRESETS, SMALL_DATASET_WARNING, EXPORTS_DIR,
    )
    from reddit_client import create_reddit_client, close_reddit_client
    from reddit_parser import parse_subreddits
    from utils.deduplication import deduplicate_posts, deduplicate_comments
    from utils.date_utils import now_utc_str, now_file_str

    # Resolve subreddits
    if args.subreddit_preset:
        subreddits = SUBREDDIT_PRESETS[args.subreddit_preset]
    else:
        subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]

    # Resolve keywords
    if args.keyword_preset:
        keywords = KEYWORD_PRESETS[args.keyword_preset]
    elif args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    else:
        keywords = []

    # Resolve run mode
    if args.run_mode:
        mode = RUN_MODES[args.run_mode]
        sort = mode["sort"]
        period = mode["period"]
        limit = args.limit if args.limit is not None else mode["limit"]
        max_comments = args.comments if args.comments is not None else mode["comments"]
        min_score = args.min_score if args.min_score is not None else mode["min_score"]
        min_comments_count = args.min_comments if args.min_comments is not None else mode["min_comments"]
    else:
        sort = args.sort
        period = args.period
        limit = args.limit if args.limit is not None else 50
        max_comments = args.comments if args.comments is not None else 20
        min_score = args.min_score if args.min_score is not None else 5
        min_comments_count = args.min_comments if args.min_comments is not None else 10

    # Auto language mode
    EN_PRESETS = {"wellness_en", "crm_en", "ai_en"}
    RU_PRESETS = {"wellness_ru"}
    UK_PRESETS = {"wellness_uk"}
    effective_language_mode = args.language_mode
    if effective_language_mode == "mixed":
        kp = args.keyword_preset or ""
        if kp in EN_PRESETS:
            effective_language_mode = "en"
        elif kp in RU_PRESETS:
            effective_language_mode = "ru"
        elif kp in UK_PRESETS:
            effective_language_mode = "uk"

    filter_bots = not args.no_bots
    fetch_selftext = not args.no_selftext

    logger.info("=" * 64)
    logger.info("Reddit Parser — parse mode")
    logger.info(f"Subreddits : {subreddits}")
    logger.info(f"Keywords   : {keywords[:5]}..." if len(keywords) > 5 else f"Keywords   : {keywords or '(all)'}")
    logger.info(f"Period: {period}  Sort: {sort}  Mode: {args.run_mode or '—'}")
    logger.info(f"Limit: {limit}/sub  Comments: {max_comments}/post")
    logger.info(f"Min score: {min_score}  Min comments: {min_comments_count}  Lang: {effective_language_mode}")
    logger.info("=" * 64)

    run_settings = {
        "run_date": now_utc_str(),
        "subreddits": ", ".join(subreddits),
        "subreddit_preset": args.subreddit_preset or "—",
        "keywords": ", ".join(keywords) if keywords else "all",
        "keyword_preset": args.keyword_preset or "—",
        "period": period, "sort": sort,
        "run_mode": args.run_mode or "—",
        "limit_per_subreddit": limit,
        "max_comments_per_post": max_comments,
        "min_score": min_score, "min_comments": min_comments_count,
        "min_comment_length": args.min_comment_length,
        "language_mode": effective_language_mode,
        "filter_bots": filter_bots, "fetch_selftext": fetch_selftext,
        "export_format": args.export,
    }

    try:
        reddit = create_reddit_client()
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        sys.exit(1)

    try:
        posts, comments = parse_subreddits(
            reddit=reddit, subreddits=subreddits, keywords=keywords,
            period=period, sort=sort, limit=limit, max_comments=max_comments,
            min_score=min_score, min_comments=min_comments_count,
            fetch_selftext=fetch_selftext, filter_bots=filter_bots,
            language_mode=effective_language_mode,
            min_comment_length=args.min_comment_length,
        )
        posts_before = len(posts)
        posts = deduplicate_posts(posts)
        comments = deduplicate_comments(comments)
        dupes = posts_before - len(posts)
        logger.info(f"Posts: {len(posts)} | Comments: {len(comments)} | Dupes removed: {dupes}")

        if len(posts) < 20:
            logger.warning(SMALL_DATASET_WARNING)

        ts = now_file_str()
        output_name = args.output or f"reddit_{ts}"
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        if args.export == "xlsx":
            from exporters.excel_exporter import export_excel
            out = os.path.join(EXPORTS_DIR, f"{output_name}.xlsx") if args.output else None
            result = export_excel(posts, comments, run_settings, out, dupes, subreddits)
            logger.info(f"Output: {result}")
        elif args.export == "csv":
            from exporters.csv_exporter import export_csv
            p, c = export_csv(posts, comments, output_name if args.output else f"reddit_{ts}")
            logger.info(f"Posts: {p}  Comments: {c}")
        elif args.export == "json":
            from exporters.json_exporter import export_json
            out = os.path.join(EXPORTS_DIR, f"{output_name}.json") if args.output else None
            result = export_json(posts, comments, run_settings, out)
            logger.info(f"Output: {result}")

        logger.info("=" * 64)
        logger.info(f"Done! {len(posts)} posts, {len(comments)} comments.")
        logger.info("=" * 64)
    finally:
        close_reddit_client(reddit)


def cmd_run_monitor(args) -> None:
    from config_loader import sync_to_db
    sync_to_db()
    from monitor_runner import run_monitor
    run = run_monitor(args.monitor_id)
    if run:
        logger.info(f"Run finished: {run.status} | Posts: {run.total_posts} | Comments: {run.total_comments}")
        if run.export_path:
            logger.info(f"Files in: {run.export_path}")


def cmd_run_all(args) -> None:
    from config_loader import get_all_monitors
    from monitor_runner import run_monitor
    monitors = get_all_monitors(enabled_only=True)
    if not monitors:
        logger.warning("No enabled monitors found")
        return
    logger.info(f"Running {len(monitors)} enabled monitors...")
    for monitor in monitors:
        logger.info(f"─── Monitor: {monitor.name} ({monitor.id}) ───")
        run_monitor(monitor.id)


def cmd_list_monitors(args) -> None:
    from config_loader import get_all_monitors
    monitors = get_all_monitors(enabled_only=False)
    if not monitors:
        logger.info("No monitors found. Check monitors.yaml")
        return
    print(f"\n{'ID':<20} {'PROJECT':<18} {'MODE':<14} {'CRON':<20} {'EN':>3}")
    print("─" * 80)
    for m in monitors:
        enabled = "✓" if m.enabled else "✗"
        print(f"{m.id:<20} {m.project_id:<18} {m.run_mode:<14} {m.schedule_cron:<20} {enabled:>3}")
    print()


def cmd_list_runs(args) -> None:
    from config_loader import sync_to_db
    sync_to_db()
    from storage import database as db
    runs = db.list_runs(limit=args.limit)
    if not runs:
        logger.info("No runs found yet. Use 'run-monitor' to start one.")
        return
    print(f"\n{'RUN ID':<14} {'MONITOR':<20} {'STATUS':<24} {'POSTS':>6} {'CMTS':>6}  STARTED")
    print("─" * 90)
    for r in runs:
        print(f"{r.id:<14} {r.monitor_id:<20} {r.status:<24} {r.total_posts:>6} {r.total_comments:>6}  {r.started_at}")
    print()


def cmd_scheduler(args) -> None:
    from scheduler_runner import start_scheduler
    start_scheduler()


# ─── Argument parser ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Multi-Monitor Trend Intelligence System v5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  parse          Direct parse (no DB). Old v4 mode.
  run-monitor    Run one monitor from monitors.yaml
  run-all        Run all enabled monitors
  list-monitors  Show all monitors
  list-runs      Show recent run history
  scheduler      Start cron scheduler daemon

Examples:
  python main.py parse --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode hot_last_7d --export xlsx
  python main.py run-monitor --monitor-id wellness_hot
  python main.py run-all
  python main.py list-monitors
  python main.py list-runs --limit 50
  python main.py scheduler
        """,
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command")

    # ── parse (legacy mode) ──────────────────────────────────────────────────
    p_parse = sub.add_parser("parse", help="Direct parse without DB (v4 mode)")
    src = p_parse.add_mutually_exclusive_group(required=True)
    src.add_argument("--subreddits")
    src.add_argument("--subreddit-preset", dest="subreddit_preset",
                     choices=["wellness_en","wellness_gut","wellness_women","wellness_energy","crm_en","ai_en","ru_uk_mixed"])
    kw = p_parse.add_mutually_exclusive_group()
    kw.add_argument("--keywords", default="")
    kw.add_argument("--keyword-preset", dest="keyword_preset",
                    choices=["wellness_en","wellness_ru","wellness_uk","crm_en","ai_en"])
    p_parse.add_argument("--period", default="last_7d",
                         choices=["last_24h","last_7d","last_30d","all"])
    p_parse.add_argument("--sort", default="hot",
                         choices=["hot","new","top","rising","controversial"])
    p_parse.add_argument("--run-mode", dest="run_mode", default=None,
                         choices=["hot_last_7d","top_week","top_month","rising_24h"])
    p_parse.add_argument("--limit", type=int, default=None)
    p_parse.add_argument("--comments", type=int, default=None)
    p_parse.add_argument("--min-score", type=int, default=None, dest="min_score")
    p_parse.add_argument("--min-comments", type=int, default=None, dest="min_comments")
    p_parse.add_argument("--min-comment-length", type=int, default=40, dest="min_comment_length")
    p_parse.add_argument("--language-mode", default="mixed",
                         choices=["en","ru","uk","mixed"], dest="language_mode")
    p_parse.add_argument("--no-bots", action="store_true", dest="no_bots")
    p_parse.add_argument("--no-selftext", action="store_true", dest="no_selftext")
    p_parse.add_argument("--export", default="xlsx", choices=["xlsx","csv","json"])
    p_parse.add_argument("--output", default=None)

    # ── run-monitor ──────────────────────────────────────────────────────────
    p_run = sub.add_parser("run-monitor", help="Run a single monitor")
    p_run.add_argument("--monitor-id", required=True, dest="monitor_id")

    # ── run-all ──────────────────────────────────────────────────────────────
    sub.add_parser("run-all", help="Run all enabled monitors")

    # ── list-monitors ────────────────────────────────────────────────────────
    sub.add_parser("list-monitors", help="List monitors from monitors.yaml")

    # ── list-runs ────────────────────────────────────────────────────────────
    p_runs = sub.add_parser("list-runs", help="Show recent run history")
    p_runs.add_argument("--limit", type=int, default=20)

    # ── scheduler ────────────────────────────────────────────────────────────
    sub.add_parser("scheduler", help="Start APScheduler daemon")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logger("DEBUG" if args.verbose else "INFO")

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "parse": cmd_parse,
        "run-monitor": cmd_run_monitor,
        "run-all": cmd_run_all,
        "list-monitors": cmd_list_monitors,
        "list-runs": cmd_list_runs,
        "scheduler": cmd_scheduler,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
