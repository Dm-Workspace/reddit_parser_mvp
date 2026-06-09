#!/usr/bin/env python3
"""Reddit Parser MVP — collect posts and comments from Reddit."""

import argparse
import sys
import os

from loguru import logger

from utils.logger import setup_logger
from config import (
    SUPPORTED_PERIODS, SUPPORTED_SORTS, SUPPORTED_EXPORTS,
    SUPPORTED_LANGUAGE_MODES, RUN_MODES, KEYWORD_PRESETS, SUBREDDIT_PRESETS,
    SMALL_DATASET_WARNING,
)
from reddit_client import create_reddit_client, close_reddit_client
from reddit_parser import parse_subreddits
from utils.deduplication import deduplicate_posts, deduplicate_comments
from utils.date_utils import now_utc_str, now_file_str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reddit Parser MVP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subreddit presets:   wellness_en, wellness_gut, wellness_women, wellness_energy, crm_en, ai_en, ru_uk_mixed
Keyword presets:     wellness_en, wellness_ru, wellness_uk, crm_en, ai_en
Run modes:           hot_last_7d, top_week, top_month, rising_24h

Examples:
  python main.py --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode hot_last_7d --export xlsx
  python main.py --subreddit-preset wellness_en --run-mode top_week --export xlsx
  python main.py --subreddits nutrition,Supplements --keywords magnesium,gut --export xlsx
  python main.py --subreddit-preset wellness_gut --run-mode rising_24h --language-mode en --export csv
        """,
    )

    # Source
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--subreddits", help="Comma-separated subreddits")
    src.add_argument("--subreddit-preset", dest="subreddit_preset",
                     choices=list(SUBREDDIT_PRESETS.keys()),
                     help="Use a built-in subreddit list")

    # Keywords
    kw = parser.add_mutually_exclusive_group()
    kw.add_argument("--keywords", default="", help="Comma-separated keywords")
    kw.add_argument("--keyword-preset", dest="keyword_preset",
                    choices=list(KEYWORD_PRESETS.keys()),
                    help="Use a built-in keyword set")

    # Sort / period / run mode
    parser.add_argument("--period", default="last_7d", choices=SUPPORTED_PERIODS)
    parser.add_argument("--sort", default="hot", choices=SUPPORTED_SORTS)
    parser.add_argument("--run-mode", dest="run_mode", default=None,
                        choices=list(RUN_MODES.keys()),
                        help="Preset that sets sort, period, limits, thresholds")

    # Limits (can be overridden even when run-mode is set)
    parser.add_argument("--limit", type=int, default=None,
                        help="Max posts per subreddit (run-mode default if omitted)")
    parser.add_argument("--comments", type=int, default=None,
                        help="Max comments per post (run-mode default if omitted)")
    parser.add_argument("--min-score", type=int, default=None, dest="min_score",
                        help="Minimum post score (run-mode default if omitted)")
    parser.add_argument("--min-comments", type=int, default=None, dest="min_comments",
                        help="Minimum post comment count (run-mode default if omitted)")
    parser.add_argument("--min-comment-length", type=int, default=40, dest="min_comment_length",
                        help="Min comment body length in chars (default: 40; bypassed if score > 10)")

    # Filters
    parser.add_argument("--language-mode", default="mixed",
                        choices=SUPPORTED_LANGUAGE_MODES, dest="language_mode")
    parser.add_argument("--no-bots", action="store_true", dest="no_bots",
                        help="Keep bot comments (they are filtered by default)")
    parser.add_argument("--no-selftext", action="store_true", dest="no_selftext",
                        help="Skip fetching post body (faster)")

    # Export
    parser.add_argument("--export", default="xlsx", choices=SUPPORTED_EXPORTS)
    parser.add_argument("--output", default=None,
                        help="Output filename without extension")
    parser.add_argument("--verbose", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logger("DEBUG" if args.verbose else "INFO")

    # Resolve subreddits
    if args.subreddit_preset:
        subreddits = SUBREDDIT_PRESETS[args.subreddit_preset]
        logger.info(f"Subreddit preset '{args.subreddit_preset}': {len(subreddits)} subreddits")
    else:
        subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]

    # Resolve keywords
    if args.keyword_preset:
        keywords = KEYWORD_PRESETS[args.keyword_preset]
        logger.info(f"Keyword preset '{args.keyword_preset}': {len(keywords)} keywords")
    elif args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    else:
        keywords = []

    # Auto language_mode: en-suffix presets default to en unless user explicitly set mixed
    EN_PRESETS = {"wellness_en", "crm_en", "ai_en"}
    RU_PRESETS = {"wellness_ru"}
    UK_PRESETS = {"wellness_uk"}
    effective_language_mode = args.language_mode
    if effective_language_mode == "mixed":  # user did not explicitly override
        kp = args.keyword_preset or ""
        if kp in EN_PRESETS:
            effective_language_mode = "en"
            logger.info("Auto language_mode=en (keyword preset is English)")
        elif kp in RU_PRESETS:
            effective_language_mode = "ru"
            logger.info("Auto language_mode=ru (keyword preset is Russian)")
        elif kp in UK_PRESETS:
            effective_language_mode = "uk"
            logger.info("Auto language_mode=uk (keyword preset is Ukrainian)")

    # Resolve run mode defaults, then apply CLI overrides
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

    filter_bots = not args.no_bots
    fetch_selftext = not args.no_selftext

    logger.info("=" * 64)
    logger.info("Reddit Parser MVP")
    logger.info(f"Subreddits     : {subreddits}")
    logger.info(f"Keywords       : {keywords[:5]}{'...' if len(keywords) > 5 else ''}" if keywords else "Keywords       : (all posts)")
    logger.info(f"Period         : {period}   Sort: {sort}   Mode: {args.run_mode or '—'}")
    logger.info(f"Limit          : {limit}/sub   Comments: {max_comments}/post")
    logger.info(f"Min score      : {min_score}   Min comments: {min_comments_count}")
    logger.info(f"Min cmnt len   : {args.min_comment_length} chars")
    logger.info(f"Language       : {effective_language_mode}   Bots: {'filtered' if filter_bots else 'kept'}")
    logger.info(f"Fetch body     : {fetch_selftext}   Export: {args.export}")
    logger.info("=" * 64)

    run_settings = {
        "run_date": now_utc_str(),
        "subreddits": ", ".join(subreddits),
        "subreddit_preset": args.subreddit_preset or "—",
        "keywords": ", ".join(keywords) if keywords else "all",
        "keyword_preset": args.keyword_preset or "—",
        "period": period,
        "sort": sort,
        "run_mode": args.run_mode or "—",
        "limit_per_subreddit": limit,
        "max_comments_per_post": max_comments,
        "min_score": min_score,
        "min_comments": min_comments_count,
        "min_comment_length": args.min_comment_length,
        "language_mode": effective_language_mode,
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
            limit=limit,
            max_comments=max_comments,
            min_score=min_score,
            min_comments=min_comments_count,
            fetch_selftext=fetch_selftext,
            filter_bots=filter_bots,
            language_mode=effective_language_mode,
            min_comment_length=args.min_comment_length,
        )

        posts_before = len(posts)
        posts = deduplicate_posts(posts)
        comments = deduplicate_comments(comments)
        dupes_removed = posts_before - len(posts)

        logger.info(f"Posts: {len(posts)} | Comments: {len(comments)} | Dupes removed: {dupes_removed}")

        if len(posts) < 20:
            logger.warning(f"Only {len(posts)} posts collected. " + SMALL_DATASET_WARNING)
        if len(comments) < 100:
            logger.warning(f"Only {len(comments)} comments collected. " + SMALL_DATASET_WARNING)

        ts = now_file_str()
        output_name = args.output or f"reddit_{ts}"

        from config import EXPORTS_DIR
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        if args.export == "xlsx":
            from exporters.excel_exporter import export_excel
            out = os.path.join(EXPORTS_DIR, f"{output_name}.xlsx") if args.output else None
            result = export_excel(posts, comments, run_settings, out, dupes_removed, subreddits)
            logger.info(f"Output: {result}")

        elif args.export == "csv":
            from exporters.csv_exporter import export_csv
            prefix = output_name if args.output else f"reddit_{ts}"
            p, c = export_csv(posts, comments, prefix)
            logger.info(f"Posts   : {p}")
            logger.info(f"Comments: {c}")

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


if __name__ == "__main__":
    main()
