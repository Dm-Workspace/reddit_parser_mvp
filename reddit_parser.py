import praw
from typing import List, Optional
from loguru import logger

from reddit_models import RedditPost, RedditComment
from reddit_filters import post_matches, comment_matches
from utils.date_utils import utc_timestamp_to_date, now_utc_str
from utils.text_cleaner import clean_body


def _get_subreddit_posts(
    reddit: praw.Reddit,
    subreddit_name: str,
    sort: str,
    limit: int,
) -> List:
    sub = reddit.subreddit(subreddit_name)
    sort_map = {
        "hot": sub.hot,
        "new": sub.new,
        "top": sub.top,
        "rising": sub.rising,
        "controversial": sub.controversial,
    }
    fetch_fn = sort_map.get(sort, sub.hot)

    try:
        if sort == "top":
            return list(fetch_fn(limit=limit, time_filter="all"))
        return list(fetch_fn(limit=limit))
    except Exception as e:
        logger.error(f"Failed to fetch posts from r/{subreddit_name}: {e}")
        return []


def _build_post(
    submission: praw.models.Submission,
    matched_keywords: List[str],
    sort_mode: str,
) -> RedditPost:
    return RedditPost(
        post_id=submission.id,
        subreddit=str(submission.subreddit),
        title=submission.title,
        selftext=clean_body(submission.selftext or ""),
        url=submission.url,
        permalink=f"https://www.reddit.com{submission.permalink}",
        created_utc=submission.created_utc,
        created_date=utc_timestamp_to_date(submission.created_utc),
        score=submission.score,
        upvote_ratio=submission.upvote_ratio,
        num_comments=submission.num_comments,
        flair=submission.link_flair_text,
        is_self=submission.is_self,
        is_video=submission.is_video,
        domain=submission.domain,
        matched_keywords=", ".join(matched_keywords),
        sort_mode=sort_mode,
        collected_at=now_utc_str(),
    )


def _fetch_comments(
    submission: praw.models.Submission,
    max_comments: int,
    keywords: List[str],
    post_id: str,
    subreddit: str,
    post_title: str,
) -> List[RedditComment]:
    try:
        submission.comments.replace_more(limit=0)
    except Exception as e:
        logger.warning(f"Could not expand comments for {post_id}: {e}")
        return []

    collected = []
    collected_at = now_utc_str()

    for comment in submission.comments.list():
        if len(collected) >= max_comments:
            break
        if not hasattr(comment, "body"):
            continue
        if comment.body in ("[deleted]", "[removed]", ""):
            continue

        matched = comment_matches(comment.body, keywords)

        collected.append(RedditComment(
            comment_id=comment.id,
            post_id=post_id,
            subreddit=subreddit,
            post_title=post_title,
            body=clean_body(comment.body),
            score=comment.score,
            created_utc=comment.created_utc,
            created_date=utc_timestamp_to_date(comment.created_utc),
            depth=comment.depth,
            permalink=f"https://www.reddit.com{comment.permalink}",
            matched_keywords=", ".join(matched),
            collected_at=collected_at,
        ))

    return collected


def parse_subreddits(
    reddit: praw.Reddit,
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

    for subreddit_name in subreddits:
        logger.info(f"Fetching r/{subreddit_name} [{sort}, limit={limit}]")
        submissions = _get_subreddit_posts(reddit, subreddit_name, sort, limit)
        logger.info(f"r/{subreddit_name}: got {len(submissions)} raw posts")

        matched_count = 0
        for submission in submissions:
            ok, matched_kws = post_matches(
                submission, keywords, period, min_score, min_comments
            )
            if not ok:
                continue

            post = _build_post(submission, matched_kws, sort)
            all_posts.append(post)
            matched_count += 1

            if max_comments > 0:
                comments = _fetch_comments(
                    submission,
                    max_comments,
                    keywords,
                    submission.id,
                    str(submission.subreddit),
                    submission.title,
                )
                all_comments.extend(comments)
                if comments:
                    logger.debug(f"  └─ {len(comments)} comments collected for '{submission.title[:60]}'")

        logger.info(f"r/{subreddit_name}: {matched_count} posts matched filters")

    return all_posts, all_comments
