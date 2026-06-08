from dataclasses import dataclass
from typing import Optional

COMMENT_MATCH_DIRECT = "direct_keyword_match"
COMMENT_MATCH_CONTEXT = "context_comment"
COMMENT_MATCH_NONE = "no_match"

CONTENT_TYPE_SELF = "self_text"
CONTENT_TYPE_IMAGE = "image"
CONTENT_TYPE_VIDEO = "video"
CONTENT_TYPE_LINK = "external_link"
CONTENT_TYPE_GALLERY = "reddit_gallery"
CONTENT_TYPE_UNKNOWN = "unknown"


def detect_content_type(raw: dict) -> str:
    if raw.get("is_self"):
        return CONTENT_TYPE_SELF
    if raw.get("is_video"):
        return CONTENT_TYPE_VIDEO
    url = raw.get("url", "")
    domain = raw.get("domain", "")
    if "reddit.com/gallery" in url or domain == "reddit.com":
        return CONTENT_TYPE_GALLERY
    if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
        return CONTENT_TYPE_IMAGE
    if domain in ("i.redd.it", "preview.redd.it", "i.imgur.com"):
        return CONTENT_TYPE_IMAGE
    if domain in ("v.redd.it", "youtube.com", "youtu.be"):
        return CONTENT_TYPE_VIDEO
    if url.startswith("http"):
        return CONTENT_TYPE_LINK
    return CONTENT_TYPE_UNKNOWN


def compute_analysis_priority(trend_score: float, num_comments: int) -> str:
    if trend_score >= 250 or num_comments >= 80:
        return "high"
    if trend_score >= 80 or num_comments >= 20:
        return "medium"
    return "low"


def detect_pain_signal(title: str, selftext: str) -> str:
    from config import PAIN_SIGNAL_MAPPING
    from utils.text_cleaner import normalize_text
    text = normalize_text(f"{title} {selftext}")
    for signal, keywords in PAIN_SIGNAL_MAPPING.items():
        if any(normalize_text(kw) in text for kw in keywords):
            return signal
    return "other"


@dataclass
class RedditPost:
    post_id: str
    subreddit: str
    title: str
    selftext: str
    url: str
    permalink: str
    created_utc: float
    created_date: str
    score: int
    upvote_ratio: float
    num_comments: int
    flair: Optional[str]
    is_self: bool
    is_video: bool
    domain: str
    matched_keywords: str
    sort_mode: str
    collected_at: str
    post_text_length: int
    language_detected: str
    trend_score: float
    content_type: str
    analysis_priority: str
    pain_signal: str

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "subreddit": self.subreddit,
            "title": self.title,
            "selftext": self.selftext,
            "url": self.url,
            "permalink": self.permalink,
            "created_utc": self.created_utc,
            "created_date": self.created_date,
            "score": self.score,
            "upvote_ratio": self.upvote_ratio,
            "num_comments": self.num_comments,
            "flair": self.flair,
            "is_self": self.is_self,
            "is_video": self.is_video,
            "domain": self.domain,
            "matched_keywords": self.matched_keywords,
            "sort_mode": self.sort_mode,
            "collected_at": self.collected_at,
            "post_text_length": self.post_text_length,
            "language_detected": self.language_detected,
            "trend_score": self.trend_score,
            "content_type": self.content_type,
            "analysis_priority": self.analysis_priority,
            "pain_signal": self.pain_signal,
        }


@dataclass
class RedditComment:
    comment_id: str
    post_id: str
    subreddit: str
    post_title: str
    author: str
    body: str
    score: int
    created_utc: float
    created_date: str
    depth: int
    permalink: str
    matched_keywords: str
    collected_at: str
    comment_text_length: int
    language_detected: str
    is_bot_comment: bool
    comment_match_type: str

    def to_dict(self) -> dict:
        return {
            "comment_id": self.comment_id,
            "post_id": self.post_id,
            "subreddit": self.subreddit,
            "post_title": self.post_title,
            "author": self.author,
            "body": self.body,
            "score": self.score,
            "created_utc": self.created_utc,
            "created_date": self.created_date,
            "depth": self.depth,
            "permalink": self.permalink,
            "matched_keywords": self.matched_keywords,
            "collected_at": self.collected_at,
            "comment_text_length": self.comment_text_length,
            "language_detected": self.language_detected,
            "is_bot_comment": self.is_bot_comment,
            "comment_match_type": self.comment_match_type,
        }
