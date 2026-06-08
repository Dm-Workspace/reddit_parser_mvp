import os
from collections import Counter, defaultdict
from typing import List, Dict, Any

import pandas as pd
from loguru import logger
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from reddit_models import RedditPost, RedditComment
from config import EXPORTS_DIR, SMALL_DATASET_MIN_POSTS, SMALL_DATASET_MIN_COMMENTS, SMALL_DATASET_WARNING
from utils.date_utils import now_file_str


def _auto_fit_columns(ws) -> None:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                cell_len = len(str(cell.value)) if cell.value else 0
                if cell_len > max_len:
                    max_len = cell_len
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)


def _style_header(ws, color: str = "2D5F8A") -> None:
    fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
    font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _build_quality_rows(
    posts: List[RedditPost],
    comments: List[RedditComment],
    duplicate_posts_removed: int,
) -> List[dict]:
    def row(metric, value):
        return {"metric": metric, "value": value}

    empty_selftext = sum(1 for p in posts if not p.selftext.strip())
    bot_comments = sum(1 for c in comments if c.is_bot_comment)
    low_score = sum(1 for p in posts if p.score < 5)
    no_kw_comments = sum(1 for c in comments if c.comment_match_type == "no_match")
    avg_comments = round(sum(p.num_comments for p in posts) / len(posts), 1) if posts else 0
    avg_score = round(sum(p.score for p in posts) / len(posts), 1) if posts else 0
    avg_cscore = round(sum(c.score for c in comments) / len(comments), 1) if comments else 0

    # Per-subreddit breakdown
    posts_per_sub = Counter(p.subreddit for p in posts)
    comments_per_sub = Counter(c.subreddit for c in comments)

    # Keyword distribution
    kw_posts: Counter = Counter()
    for p in posts:
        for kw in p.matched_keywords.split(", "):
            if kw.strip():
                kw_posts[kw.strip()] += 1

    kw_comments: Counter = Counter()
    for c in comments:
        for kw in c.matched_keywords.split(", "):
            if kw.strip():
                kw_comments[kw.strip()] += 1

    # Language distribution
    post_lang = Counter(p.language_detected for p in posts)
    comment_lang = Counter(c.language_detected for c in comments)

    rows = [
        row("=== OVERVIEW ===", ""),
        row("total_posts", len(posts)),
        row("total_comments", len(comments)),
        row("duplicate_posts_removed", duplicate_posts_removed),
        row("", ""),
        row("=== DATA QUALITY ===", ""),
        row("empty_selftext_count", empty_selftext),
        row("bot_comments_filtered", bot_comments),
        row("low_score_posts (score<5)", low_score),
        row("comments_no_keyword_match", no_kw_comments),
        row("average_comments_per_post", avg_comments),
        row("average_post_score", avg_score),
        row("average_comment_score", avg_cscore),
    ]

    if len(posts) < SMALL_DATASET_MIN_POSTS or len(comments) < SMALL_DATASET_MIN_COMMENTS:
        rows.append(row("⚠ DATASET WARNING", SMALL_DATASET_WARNING))

    rows.append(row("", ""))
    rows.append(row("=== POSTS PER SUBREDDIT ===", ""))
    for sub, cnt in sorted(posts_per_sub.items(), key=lambda x: -x[1]):
        rows.append(row(f"  r/{sub}", cnt))

    rows.append(row("", ""))
    rows.append(row("=== COMMENTS PER SUBREDDIT ===", ""))
    for sub, cnt in sorted(comments_per_sub.items(), key=lambda x: -x[1]):
        rows.append(row(f"  r/{sub}", cnt))

    rows.append(row("", ""))
    rows.append(row("=== TOP KEYWORDS IN POSTS ===", ""))
    for kw, cnt in kw_posts.most_common(20):
        rows.append(row(f"  {kw}", cnt))

    rows.append(row("", ""))
    rows.append(row("=== TOP KEYWORDS IN COMMENTS ===", ""))
    for kw, cnt in kw_comments.most_common(20):
        rows.append(row(f"  {kw}", cnt))

    rows.append(row("", ""))
    rows.append(row("=== POST LANGUAGE DISTRIBUTION ===", ""))
    for lang, cnt in sorted(post_lang.items()):
        rows.append(row(f"  {lang}", cnt))

    rows.append(row("", ""))
    rows.append(row("=== COMMENT LANGUAGE DISTRIBUTION ===", ""))
    for lang, cnt in sorted(comment_lang.items()):
        rows.append(row(f"  {lang}", cnt))

    return rows


def export_excel(
    posts: List[RedditPost],
    comments: List[RedditComment],
    run_settings: Dict[str, Any],
    output_path: str = None,
    duplicate_posts_removed: int = 0,
) -> str:
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    if not output_path:
        output_path = os.path.join(EXPORTS_DIR, f"reddit_{now_file_str()}.xlsx")

    small_dataset = (
        len(posts) < SMALL_DATASET_MIN_POSTS or
        len(comments) < SMALL_DATASET_MIN_COMMENTS
    )

    summary = {
        "run_date": run_settings.get("run_date", ""),
        "subreddits": run_settings.get("subreddits", ""),
        "keywords": run_settings.get("keywords", ""),
        "period": run_settings.get("period", ""),
        "sort": run_settings.get("sort", ""),
        "total_posts": len(posts),
        "total_comments": len(comments),
        "min_score": run_settings.get("min_score", 0),
        "min_comments": run_settings.get("min_comments", 0),
        "max_comments_per_post": run_settings.get("max_comments_per_post", 0),
        "language_mode": run_settings.get("language_mode", "mixed"),
        "dataset_warning": SMALL_DATASET_WARNING if small_dataset else "OK",
    }

    posts_data = [p.to_dict() for p in posts]
    comments_data = [c.to_dict() for c in comments]
    quality_rows = _build_quality_rows(posts, comments, duplicate_posts_removed)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
        ws = writer.sheets["Summary"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        df_posts = pd.DataFrame(posts_data) if posts_data else pd.DataFrame(columns=list(RedditPost.__dataclass_fields__.keys()))
        df_posts.to_excel(writer, sheet_name="Posts", index=False)
        ws = writer.sheets["Posts"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        df_comments = pd.DataFrame(comments_data) if comments_data else pd.DataFrame(columns=list(RedditComment.__dataclass_fields__.keys()))
        df_comments.to_excel(writer, sheet_name="Comments", index=False)
        ws = writer.sheets["Comments"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        settings_rows = [{"parameter": k, "value": str(v)} for k, v in run_settings.items()]
        pd.DataFrame(settings_rows).to_excel(writer, sheet_name="Run Settings", index=False)
        ws = writer.sheets["Run Settings"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        pd.DataFrame(quality_rows).to_excel(writer, sheet_name="Quality Check", index=False)
        ws = writer.sheets["Quality Check"]
        _style_header(ws, "4A7C59")
        _auto_fit_columns(ws)

    if small_dataset:
        logger.warning(SMALL_DATASET_WARNING)

    logger.success(f"Excel exported: {output_path}")
    return output_path
