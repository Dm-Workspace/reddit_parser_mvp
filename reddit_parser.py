import time
import requests
from typing import List, Optional
from loguru import logger

from reddit_models import RedditPost, RedditComment
from reddit_filters import post_matches_data, comment_matches
from utils.date_utils import utc_timestamp_to_date, now_utc_str, get_cutoff_timestamp
from utils.text_cleaner import clean_body

BASE_URL = "https://www.reddit.com"
OLD_BASE_URL = "https://old.reddit.com"


def _fetch_json(session: requests.Session, url: str, params: dict = None) -> Optional[dict]:
    urls_to_try = [url, url.replace("www.reddit.com", "old.reddit.com")]
    for attempt_url in urls_to_try:
        try:
            time.sleep(1.5)
            resp = session.get(attempt_url, params=params, timeout=20)
            if resp.status_code == 429:
                logger.warning("Rate limited by Reddit, waiting 15s...")
                time.sleep(15)
                resp = session.get(attempt_url, params=params, timeout=20)
            if resp.status_code == 403:
                logger.debug(f"403 on {attempt_url}, trying fallback...")
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"Attempt failed: {attempt_url} — {e}")
            continue
    logger.error(f"All attempts failed for: {url}")
    return None


def _get_posts_raw(
    session: requests.Session,
    subreddit: str,
    sort: str,
    limit: int,
) -> List[dict]:
    url = f"{BASE_URL}/r/{subreddit}/{sort}.json"
    collected = []
    after = None

    while len(collected) < limit:
        batch_size = min(100, limit - len(collected))
        params = {"limit": batch_size, "raw_json": 1}
        if after:
            params["after"] = after

        data = _fetch_json(session, url, params)
        if not data:
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for child in children:
            collected.append(child.get("data", {}))

        after = data.get("data", {}).get("after")
        if not after:
            break

        time.sleep(1)

    return collected[:limit]


def _get_comments_raw(
    session: requests.Session,
    subreddit: str,
    post_id: str,
    max_comments: int,
) -> List[dict]:
    url = f"{BASE_URL}/r/{subreddit}/comments/{post_id}.json"
    params = {"limit": max_comments, "depth": 3, "raw_json": 1}
    data = _fetch_json(session, url, params)
    if not data or len(data) < 2:
        return []

    comments = []
    comment_listing = data[1].get("data", {}).get("children", [])
    _flatten_comments(comment_listing, comments, max_comments, depth=0)
    return comments


def _flatten_comments(children: List[dict], result: List[dict], limit: int, depth: int) -> None:
    for child in children:
        if len(result) >= limit:
            break
        kind = child.get("kind")
        if kind != "t1":
            continue
        data = child.get("data", {})
        data["_depth"] = depth
        result.append(data)
        replies = data.get("replies")
        if isinstance(replies, dict):
            sub_children = replies.get("data", {}).get("children", [])
            _flatten_comments(sub_children, result, limit, depth + 1)


def _build_post(raw: dict, matched_keywords: List[str], sort_mode: str) -> RedditPost:
    return RedditPost(
        post_id=raw.get("id", ""),
        subreddit=raw.get("subreddit", ""),
        title=raw.get("title", ""),
        selftext=clean_body(raw.get("selftext", "")),
        url=raw.get("url", ""),
        permalink=f"{BASE_URL}{raw.get('permalink', '')}",
        created_utc=raw.get("created_utc", 0),
        created_date=utc_timestamp_to_date(raw.get("created_utc", 0)),
        score=raw.get("score", 0),
        upvote_ratio=raw.get("upvote_ratio", 0.0),
        num_comments=raw.get("num_comments", 0),
        flair=raw.get("link_flair_text"),
        is_self=raw.get("is_self", False),
        is_video=raw.get("is_video", False),
        domain=raw.get("domain", ""),
        matched_keywords=", ".join(matched_keywords),
        sort_mode=sort_mode,
        collected_at=now_utc_str(),
    )


def _build_comment(raw: dict, post_id: str, subreddit: str, post_title: str, keywords: List[str]) -> RedditComment:
    matched = comment_matches(raw.get("body", ""), keywords)
    return RedditComment(
        comment_id=raw.get("id", ""),
        post_id=post_id,
        subreddit=subreddit,
        post_title=post_title,
        body=clean_body(raw.get("body", "")),
        score=raw.get("score", 0),
        created_utc=raw.get("created_utc", 0),
        created_date=utc_timestamp_to_date(raw.get("created_utc", 0)),
        depth=raw.get("_depth", 0),
        permalink=f"{BASE_URL}{raw.get('permalink', '')}",
        matched_keywords=", ".join(matched),
        collected_at=now_utc_str(),
    )


def parse_subreddits(
    reddit: requests.Session,
    subreddits: List[str],
    keywords: List[str],
    period: str,
    sort: str,
    limit: int,
    max_comments: int,
    min_score: int,
    min_comments: int,
) -> tuple[List[RedditPost], List[RedditComment]]:
    all_posts: List[RedditPost] = []
    all_comments: List[RedditComment] = []
    cutoff = get_cutoff_timestamp(period)

    for subreddit_name in subreddits:
        logger.info(f"Fetching r/{subreddit_name} [{sort}, limit={limit}]")
        raw_posts = _get_posts_raw(reddit, subreddit_name, sort, limit)
        logger.info(f"r/{subreddit_name}: got {len(raw_posts)} raw posts")

        matched_count = 0
        for raw in raw_posts:
            ok, matched_kws = post_matches_data(raw, keywords, cutoff, min_score, min_comments)
            if not ok:
                continue

            post = _build_post(raw, matched_kws, sort)
            all_posts.append(post)
            matched_count += 1

            if max_comments > 0:
                raw_comments = _get_comments_raw(
                    reddit, subreddit_name, raw["id"], max_comments
                )
                for rc in raw_comments:
                    comment = _build_comment(rc, raw["id"], subreddit_name, raw.get("title", ""), keywords)
                    all_comments.append(comment)
                if raw_comments:
                    logger.debug(f"  └─ {len(raw_comments)} comments for '{raw.get('title', '')[:60]}'")
                time.sleep(0.5)

        logger.info(f"r/{subreddit_name}: {matched_count} posts matched filters")

    return all_posts, all_comments
