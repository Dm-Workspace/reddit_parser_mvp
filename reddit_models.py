from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


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
        }


@dataclass
class RedditComment:
    comment_id: str
    post_id: str
    subreddit: str
    post_title: str
    body: str
    score: int
    created_utc: float
    created_date: str
    depth: int
    permalink: str
    matched_keywords: str
    collected_at: str

    def to_dict(self) -> dict:
        return {
            "comment_id": self.comment_id,
            "post_id": self.post_id,
            "subreddit": self.subreddit,
            "post_title": self.post_title,
            "body": self.body,
            "score": self.score,
            "created_utc": self.created_utc,
            "created_date": self.created_date,
            "depth": self.depth,
            "permalink": self.permalink,
            "matched_keywords": self.matched_keywords,
            "collected_at": self.collected_at,
        }
