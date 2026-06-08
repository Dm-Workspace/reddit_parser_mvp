import os
import pandas as pd
from typing import List, Dict, Any
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


def _style_header(ws) -> None:
    header_fill = PatternFill(start_color="2D5F8A", end_color="2D5F8A", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def export_excel(
    posts: List[RedditPost],
    comments: List[RedditComment],
    run_settings: Dict[str, Any],
    output_path: str = None,
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
    }

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Summary sheet
        df_summary = pd.DataFrame([summary])
        df_summary.to_excel(writer, sheet_name="Summary", index=False)
        ws = writer.sheets["Summary"]
        _style_header(ws)
        _auto_fit_columns(ws)

        # Posts sheet
        if posts_data:
            df_posts = pd.DataFrame(posts_data)
        else:
            df_posts = pd.DataFrame(columns=list(RedditPost.__dataclass_fields__.keys()))
        df_posts.to_excel(writer, sheet_name="Posts", index=False)
        ws = writer.sheets["Posts"]
        _style_header(ws)
        _auto_fit_columns(ws)

        # Comments sheet
        if comments_data:
            df_comments = pd.DataFrame(comments_data)
        else:
            df_comments = pd.DataFrame(columns=list(RedditComment.__dataclass_fields__.keys()))
        df_comments.to_excel(writer, sheet_name="Comments", index=False)
        ws = writer.sheets["Comments"]
        _style_header(ws)
        _auto_fit_columns(ws)

        # Run Settings sheet
        settings_rows = [{"parameter": k, "value": str(v)} for k, v in run_settings.items()]
        df_settings = pd.DataFrame(settings_rows)
        df_settings.to_excel(writer, sheet_name="Run Settings", index=False)
        ws = writer.sheets["Run Settings"]
        _style_header(ws)
        _auto_fit_columns(ws)

    logger.success(f"Excel exported: {output_path}")
    return output_path
