import os
import json
from typing import List, Dict, Any
from loguru import logger

from reddit_models import RedditPost, RedditComment
from config import EXPORTS_DIR
from utils.date_utils import now_file_str


def export_json(
    posts: List[RedditPost],
    comments: List[RedditComment],
    run_settings: Dict[str, Any],
    output_path: str = None,
) -> str:
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    if not output_path:
        output_path = os.path.join(EXPORTS_DIR, f"reddit_{now_file_str()}.json")

    payload = {
        "summary": {
            **run_settings,
            "total_posts": len(posts),
            "total_comments": len(comments),
        },
        "posts": [p.to_dict() for p in posts],
        "comments": [c.to_dict() for c in comments],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.success(f"JSON exported: {output_path}")
    return output_path
