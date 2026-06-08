from typing import List, Optional
from loguru import logger

import praw.models

from utils.date_utils import get_cutoff_timestamp
from utils.text_cleaner import normalize_text


def matches_keywords(text: str, keywords: List[str]) -> List[str]:
    if not keywords:
        return []
    norm = normalize_text(text)
    return [kw for kw in keywords if normalize_text(kw) in norm]


def post_matches(
    submission: praw.models.Submission,
    keywords: List[str],
    period: str,
    min_score: int,
    min_comments: int,
) -> tuple[bool, List[str]]:
    cutoff = get_cutoff_timestamp(period)
    if cutoff and submission.created_utc < cutoff:
        return False, []

    if submission.score < min_score:
        return False, []

    if submission.num_comments < min_comments:
        return False, []

    if not keywords:
        return True, []

    combined = f"{submission.title} {submission.selftext or ''}"
    matched = matches_keywords(combined, keywords)
    return bool(matched), matched


def comment_matches(body: str, keywords: List[str]) -> List[str]:
    if not keywords:
        return []
    return matches_keywords(body, keywords)
