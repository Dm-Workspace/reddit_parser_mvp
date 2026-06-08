#!/usr/bin/env python3
"""
Reddit Parser MVP
CLI tool to collect posts and comments from Reddit subreddits.
"""

import argparse
import sys
import os

from loguru import logger

from utils.logger import setup_logger
from config import (
    SUPPORTED_PERIODS, SUPPORTED_SORTS, SUPPORTED_EXPORTS,
    SUPPORTED_LANGUAGE_MODES, RUN_MODES, KEYWORD_PRESETS,
)
from reddit_client import create_reddit_client, close_reddit_client
from reddit_parser import parse_subreddits
from utils.deduplication import deduplicate_posts, deduplicate_comments
from utils.date_utils import now_utc_str, now_file_str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reddit Parser MVP — collect posts and comments from Reddit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Run mode shortcuts (override --sort and --period):
  --run-mode hot_last_7d    hot + last_7d
  --run-mode top_week       top + last_7d
  --run-mode rising_24h     rising + last_24h

Keyword presets (use instead of --keywords):
  wellness_en, wellness_ru, wellness_uk, crm_en, ai_en

Examples:
  python main.py --subreddits nutrition,Supplements --keywords magnesium,vitamin --export xlsx
  python main.py --subreddits Biohackers --run-mode top_week --limit 100 --export csv
  python main.py --subreddits nutrition --keyword-preset wellness_en --export xlsx
  python main.py --subreddits keto --export json --language-mode en --no-bots
        """,
    )

    parser.add_argument("--subreddits", required=True,
                        help="Comma-separated subreddits")
    parser.add_argument("--keywords", default="",
                        help="Comma-separated keywords (if omitted, all posts collected)")
    parser.add_argument("--keyword-preset", default=None,
                        choices=list(KEYWORD_PRESETS.keys()),
                        help="Use a built-in keyword preset instead of --keywords")
    parser.add_argument("--period", default="last_7d", choices=SUPPORTED_PERIODS)
    parser.add_argument("--sort", default="hot", choices=SUPPORTED_SORTS)
    parser.add_argument("--run-mode", default=None, choices=list(RUN_MODES.keys()),
                        help="Preset combination of --sort and --period")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max posts per subreddit (default: 50)")
    parser.add_argument("--comments", type=int, default=20,
                        help="Max comments per post (default: 20, 0=skip)")
    parser.add_argument("--min-score", type=int, default=5, dest="min_score",
                        help="Minimum post score (default: 5)")
    parser.add_argument("--min-comments", type=int, default=10, dest="min_comments",
                        help="Minimum post comment count (default: 10)")
    parser.add_argument("--export", default="xlsx", choices=SUPPORTED_EXPORTS)
    parser.add_argument("--output", default=None,
                        help="Output filename without extension (auto-generated if omitted)")
    parser.add_argument("--language-mode", default="mixed",
                        choices=SUPPORTED_LANGUAGE_MODES, dest="language_mode",
                        help="Filter by language: en/ru/uk/mixed (default: mixed)")
    parser.add_argument("--no-bots", action="store_true", dest="no_bots",
                        help="Filter out bot comments (AutoModerator etc.) — enabled by default")
    parser.add_argument("--no-selftext", action="store_true", dest="no_selftext",
                        help="Skip fetching selftext (faster but loses post body)")
    parser.add_argument("--verbose", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logger("DEBUG" if args.verbose else "INFO")

    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]

    # Resolve run mode
    sort = args.sort
    period = args.period
    if args.run_mode:
        sort, period = RUN_MODES[args.run_mode]
        logger.info(f"Run mode '{args.run_mode}': sort={sort}, period={period}")

    # Resolve keywords
    if args.keyword_preset:
        keywords = KEYWORD_PRESETS[args.keyword_preset]
        logger.info(f"Keyword preset '{args.keyword_preset}': {len(keywords)} keywords")
    elif args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    else:
        keywords = []

    filter_bots = not args.no_bots
    fetch_selftext = not args.no_selftext

    logger.info("=" * 60)
    logger.info("Reddit Parser MVP")
    logger.info(f"Subreddits   : {subreddits}")
    logger.info(f"Keywords     : {keywords if keywords else '(all posts)'}")
    logger.info(f"Period       : {period}")
    logger.info(f"Sort         : {sort}")
    logger.info(f"Limit        : {args.limit} posts/subreddit")
    logger.info(f"Comments     : {args.comments} per post")
    logger.info(f"Min score    : {args.min_score}")
    logger.info(f"Min comments : {args.min_comments}")
    logger.info(f"Language     : {args.language_mode}")
    logger.info(f"Filter bots  : {filter_bots}")
    logger.info(f"Fetch body   : {fetch_selftext}")
    logger.info(f"Export       : {args.export}")
    logger.info("=" * 60)

    run_settings = {
        "run_date": now_utc_str(),
        "subreddits": ", ".join(subreddits),
        "keywords": ", ".join(keywords) if keywords else "all",
        "keyword_preset": args.keyword_preset or "—",
        "period": period,
        "sort": sort,
        "run_mode": args.run_mode or "—",
        "limit_per_subreddit": args.limit,
        "max_comments_per_post": args.comments,
        "min_score": args.min_score,
        "min_comments": args.min_comments,
        "language_mode": args.language_mode,
        "filter_bots": filter_bots,
        "fetch_selftext": fetch_selftext,
        "export_format": args.export,
    }

    try:
        reddit = create_reddit_client()
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        sys.exit(1)

    try:
        posts, comments = parse_subreddits(
            reddit=reddit,
            subreddits=subreddits,
            keywords=keywords,
            period=period,
            sort=sort,
            limit=args.limit,
            max_comments=args.comments,
            min_score=args.min_score,
            min_comments=args.min_comments,
            fetch_selftext=fetch_selftext,
            filter_bots=filter_bots,
            language_mode=args.language_mode,
        )

        posts_before = len(posts)
        posts = deduplicate_posts(posts)
        comments = deduplicate_comments(comments)
        duplicate_posts_removed = posts_before - len(posts)

        logger.info(f"Posts: {len(posts)} | Comments: {len(comments)} | Duplicates removed: {duplicate_posts_removed}")

        if not posts:
            logger.warning("No posts collected. Try wider keywords, lower --min-score, or different subreddits.")

        ts = now_file_str()
        output_name = args.output or f"reddit_{ts}"

        from config import EXPORTS_DIR
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        if args.export == "xlsx":
            from exporters.excel_exporter import export_excel
            output_path = os.path.join(EXPORTS_DIR, f"{output_name}.xlsx") if args.output else None
            result = export_excel(posts, comments, run_settings, output_path, duplicate_posts_removed)
            logger.info(f"Output file: {result}")

        elif args.export == "csv":
            from exporters.csv_exporter import export_csv
            prefix = output_name if args.output else f"reddit_{ts}"
            posts_path, comments_path = export_csv(posts, comments, prefix)
            logger.info(f"Posts   : {posts_path}")
            logger.info(f"Comments: {comments_path}")

        elif args.export == "json":
            from exporters.json_exporter import export_json
            output_path = os.path.join(EXPORTS_DIR, f"{output_name}.json") if args.output else None
            result = export_json(posts, comments, run_settings, output_path)
            logger.info(f"Output file: {result}")

        logger.info("=" * 60)
        logger.info(f"Done! {len(posts)} posts, {len(comments)} comments.")
        logger.info("=" * 60)

    finally:
        close_reddit_client(reddit)


if __name__ == "__main__":
    main()
