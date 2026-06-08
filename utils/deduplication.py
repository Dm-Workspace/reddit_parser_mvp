from typing import List
from loguru import logger

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

from utils.text_cleaner import normalize_text
from reddit_models import RedditPost, RedditComment


def deduplicate_posts(posts: List[RedditPost], fuzzy_threshold: int = 85) -> List[RedditPost]:
    seen_ids = set()
    seen_permalinks = set()
    seen_titles = set()
    unique = []

    for post in posts:
        if post.post_id in seen_ids:
            continue
        if post.permalink in seen_permalinks:
            continue

        norm_title = normalize_text(post.title)
        if norm_title in seen_titles:
            continue

        if RAPIDFUZZ_AVAILABLE and fuzzy_threshold < 100:
            is_duplicate = False
            for existing_title in seen_titles:
                if fuzz.ratio(norm_title, existing_title) >= fuzzy_threshold:
                    logger.debug(f"Fuzzy duplicate found: '{post.title}'")
                    is_duplicate = True
                    break
            if is_duplicate:
                continue

        seen_ids.add(post.post_id)
        seen_permalinks.add(post.permalink)
        seen_titles.add(norm_title)
        unique.append(post)

    removed = len(posts) - len(unique)
    if removed > 0:
        logger.info(f"Deduplication removed {removed} duplicate posts")
    return unique


def deduplicate_comments(comments: List[RedditComment]) -> List[RedditComment]:
    seen_ids = set()
    unique = []
    for comment in comments:
        if comment.comment_id not in seen_ids:
            seen_ids.add(comment.comment_id)
            unique.append(comment)
    return unique
