import os
import pandas as pd
from typing import List
from loguru import logger

from reddit_models import RedditPost, RedditComment
from config import EXPORTS_DIR
from utils.date_utils import now_file_str


def export_csv(
    posts: List[RedditPost],
    comments: List[RedditComment],
    output_prefix: str = None,
) -> tuple[str, str]:
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ts = now_file_str()
    prefix = output_prefix or f"reddit_{ts}"

    posts_path = os.path.join(EXPORTS_DIR, f"{prefix}_posts.csv")
    comments_path = os.path.join(EXPORTS_DIR, f"{prefix}_comments.csv")

    posts_data = [p.to_dict() for p in posts]
    comments_data = [c.to_dict() for c in comments]

    if posts_data:
        pd.DataFrame(posts_data).to_csv(posts_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(posts_path, index=False)

    if comments_data:
        pd.DataFrame(comments_data).to_csv(comments_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(comments_path, index=False)

    logger.success(f"CSV exported: {posts_path}")
    logger.success(f"CSV exported: {comments_path}")
    return posts_path, comments_path
