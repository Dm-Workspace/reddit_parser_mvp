from typing import List, Optional, Tuple
from utils.text_cleaner import normalize_text


def matches_keywords(text: str, keywords: List[str]) -> List[str]:
    if not keywords:
        return []
    norm = normalize_text(text)
    return [kw for kw in keywords if normalize_text(kw) in norm]


def post_matches_data(
    raw: dict,
    keywords: List[str],
    cutoff: Optional[float],
    min_score: int,
    min_comments: int,
) -> Tuple[bool, List[str]]:
    if cutoff and raw.get("created_utc", 0) < cutoff:
        return False, []
    if raw.get("score", 0) < min_score:
        return False, []
    if raw.get("num_comments", 0) < min_comments:
        return False, []

    if not keywords:
        return True, []

    combined = f"{raw.get('title', '')} {raw.get('selftext', '')}"
    matched = matches_keywords(combined, keywords)
    return bool(matched), matched


def comment_matches(body: str, keywords: List[str]) -> List[str]:
    if not keywords:
        return []
    return matches_keywords(body, keywords)
