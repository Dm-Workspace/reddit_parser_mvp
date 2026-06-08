import os
from collections import Counter
from typing import List, Dict, Any

import pandas as pd
from loguru import logger
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from reddit_models import RedditPost, RedditComment
from config import EXPORTS_DIR
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
    header_fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _build_quality_check(
    posts: List[RedditPost],
    comments: List[RedditComment],
    duplicate_posts_removed: int,
) -> List[dict]:
    empty_selftext = sum(1 for p in posts if not p.selftext.strip())
    bot_comments = sum(1 for c in comments if c.is_bot_comment)
    low_score_posts = sum(1 for p in posts if p.score < 5)
    comments_no_kw = sum(1 for c in comments if not c.matched_keywords)

    post_lang_dist = Counter(p.language_detected for p in posts)
    comment_lang_dist = Counter(c.language_detected for c in comments)

    rows = [
        {"metric": "total_posts", "value": len(posts)},
        {"metric": "total_comments", "value": len(comments)},
        {"metric": "empty_selftext_count", "value": empty_selftext},
        {"metric": "bot_comments_count", "value": bot_comments},
        {"metric": "low_score_posts_count (score<5)", "value": low_score_posts},
        {"metric": "duplicate_posts_removed", "value": duplicate_posts_removed},
        {"metric": "comments_without_keywords", "value": comments_no_kw},
        {"metric": "--- post language distribution ---", "value": ""},
    ]
    for lang, count in sorted(post_lang_dist.items()):
        rows.append({"metric": f"  posts_lang_{lang}", "value": count})

    rows.append({"metric": "--- comment language distribution ---", "value": ""})
    for lang, count in sorted(comment_lang_dist.items()):
        rows.append({"metric": f"  comments_lang_{lang}", "value": count})

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

    posts_data = [p.to_dict() for p in posts]
    comments_data = [c.to_dict() for c in comments]

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
    }

    quality_rows = _build_quality_check(posts, comments, duplicate_posts_removed)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Summary
        pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
        ws = writer.sheets["Summary"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        # Posts
        if posts_data:
            df_posts = pd.DataFrame(posts_data)
        else:
            df_posts = pd.DataFrame(columns=list(RedditPost.__dataclass_fields__.keys()))
        df_posts.to_excel(writer, sheet_name="Posts", index=False)
        ws = writer.sheets["Posts"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        # Comments
        if comments_data:
            df_comments = pd.DataFrame(comments_data)
        else:
            df_comments = pd.DataFrame(columns=list(RedditComment.__dataclass_fields__.keys()))
        df_comments.to_excel(writer, sheet_name="Comments", index=False)
        ws = writer.sheets["Comments"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        # Run Settings
        settings_rows = [{"parameter": k, "value": str(v)} for k, v in run_settings.items()]
        pd.DataFrame(settings_rows).to_excel(writer, sheet_name="Run Settings", index=False)
        ws = writer.sheets["Run Settings"]
        _style_header(ws, "2D5F8A")
        _auto_fit_columns(ws)

        # Quality Check
        pd.DataFrame(quality_rows).to_excel(writer, sheet_name="Quality Check", index=False)
        ws = writer.sheets["Quality Check"]
        _style_header(ws, "4A7C59")
        _auto_fit_columns(ws)

    logger.success(f"Excel exported: {output_path}")
    return output_path
