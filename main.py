#!/usr/bin/env python3
"""
Reddit Parser MVP
CLI tool to collect posts and comments from Reddit subreddits.
"""

import argparse
import sys
import os
from datetime import datetime

from loguru import logger

from utils.logger import setup_logger
from config import SUPPORTED_PERIODS, SUPPORTED_SORTS, SUPPORTED_EXPORTS
from reddit_client import create_reddit_client
from reddit_parser import parse_subreddits
from utils.deduplication import deduplicate_posts, deduplicate_comments
from utils.date_utils import now_utc_str, now_file_str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reddit Parser MVP — collect posts and comments from Reddit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --subreddits nutrition,Supplements --keywords fatigue,magnesium --export xlsx
  python main.py --subreddits Biohackers --period last_30d --sort top --limit 100 --export csv
  python main.py --subreddits fitness --export json --output my_report
        """,
    )

    parser.add_argument(
        "--subreddits",
        required=True,
        help="Comma-separated list of subreddits (e.g. nutrition,Supplements)",
    )
    parser.add_argument(
        "--keywords",
        default="",
        help="Comma-separated list of keywords. If omitted, all posts are collected.",
    )
    parser.add_argument(
        "--period",
        default="last_7d",
        choices=SUPPORTED_PERIODS,
        help="Time period filter (default: last_7d)",
    )
    parser.add_argument(
        "--sort",
        default="hot",
        choices=SUPPORTED_SORTS,
        help="Sort mode for posts (default: hot)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max posts per subreddit (default: 50)",
    )
    parser.add_argument(
        "--comments",
        type=int,
        default=20,
        help="Max top comments per post (default: 20, 0 = skip)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        dest="min_score",
        help="Minimum post score (default: 0)",
    )
    parser.add_argument(
        "--min-comments",
        type=int,
        default=0,
        dest="min_comments",
        help="Minimum number of comments on post (default: 0)",
    )
    parser.add_argument(
        "--export",
        default="xlsx",
        choices=SUPPORTED_EXPORTS,
        help="Export format: xlsx, csv, json (default: xlsx)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output filename (without extension). Auto-generated if omitted.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logger("DEBUG" if args.verbose else "INFO")

    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []

    logger.info("=" * 60)
    logger.info("Reddit Parser MVP")
    logger.info(f"Subreddits : {subreddits}")
    logger.info(f"Keywords   : {keywords if keywords else '(all posts)'}")
    logger.info(f"Period     : {args.period}")
    logger.info(f"Sort       : {args.sort}")
    logger.info(f"Limit      : {args.limit} posts/subreddit")
    logger.info(f"Comments   : {args.comments} per post")
    logger.info(f"Min score  : {args.min_score}")
    logger.info(f"Min cmts   : {args.min_comments}")
    logger.info(f"Export     : {args.export}")
    logger.info("=" * 60)

    run_settings = {
        "run_date": now_utc_str(),
        "subreddits": ", ".join(subreddits),
        "keywords": ", ".join(keywords) if keywords else "all",
        "period": args.period,
        "sort": args.sort,
        "limit_per_subreddit": args.limit,
        "max_comments_per_post": args.comments,
        "min_score": args.min_score,
        "min_comments": args.min_comments,
        "export_format": args.export,
    }

    try:
        reddit = create_reddit_client()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    posts, comments = parse_subreddits(
        reddit=reddit,
        subreddits=subreddits,
        keywords=keywords,
        period=args.period,
        sort=args.sort,
        limit=args.limit,
        max_comments=args.comments,
        min_score=args.min_score,
        min_comments=args.min_comments,
    )

    logger.info(f"Before deduplication: {len(posts)} posts, {len(comments)} comments")
    posts = deduplicate_posts(posts)
    comments = deduplicate_comments(comments)
    logger.info(f"After deduplication : {len(posts)} posts, {len(comments)} comments")

    if not posts:
        logger.warning("No posts collected. Check your filters, keywords, or subreddit names.")

    ts = now_file_str()
    output_name = args.output or f"reddit_{ts}"

    from config import EXPORTS_DIR
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    if args.export == "xlsx":
        from exporters.excel_exporter import export_excel
        output_path = os.path.join(EXPORTS_DIR, f"{output_name}.xlsx") if args.output else None
        result = export_excel(posts, comments, run_settings, output_path)
        logger.info(f"Output file: {result}")

    elif args.export == "csv":
        from exporters.csv_exporter import export_csv
        prefix = output_name if args.output else f"reddit_{ts}"
        posts_path, comments_path = export_csv(posts, comments, prefix)
        logger.info(f"Posts file   : {posts_path}")
        logger.info(f"Comments file: {comments_path}")

    elif args.export == "json":
        from exporters.json_exporter import export_json
        output_path = os.path.join(EXPORTS_DIR, f"{output_name}.json") if args.output else None
        result = export_json(posts, comments, run_settings, output_path)
        logger.info(f"Output file: {result}")

    logger.info("=" * 60)
    logger.info(f"Done! {len(posts)} posts, {len(comments)} comments collected.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
