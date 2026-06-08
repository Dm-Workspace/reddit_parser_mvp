from dataclasses import dataclass
from typing import Optional

COMMENT_MATCH_DIRECT = "direct_keyword_match"
COMMENT_MATCH_CONTEXT = "context_comment"
COMMENT_MATCH_NONE = "no_match"


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
    comment_match_type: str  # direct_keyword_match | context_comment | no_match

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
