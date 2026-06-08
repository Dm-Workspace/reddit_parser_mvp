import time
import re
from typing import List, Optional
from loguru import logger
from playwright.sync_api import BrowserContext, Page

from reddit_models import RedditPost, RedditComment
from reddit_filters import post_matches_data, comment_matches
from utils.date_utils import utc_timestamp_to_date, now_utc_str, get_cutoff_timestamp
from utils.text_cleaner import clean_body

BASE_URL = "https://www.reddit.com"
OLD_BASE_URL = "https://old.reddit.com"


def _load_page(context: BrowserContext, url: str) -> Optional[Page]:
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.5)
        return page
    except Exception as e:
        logger.debug(f"Failed to load {url}: {e}")
        page.close()
        return None


def _parse_timestamp(data_timestamp: str) -> float:
    try:
        return float(data_timestamp)
    except Exception:
        return 0.0


def _get_posts_raw(
    context: BrowserContext,
    subreddit: str,
    sort: str,
    limit: int,
) -> List[dict]:
    collected = []
    after = None

    while len(collected) < limit:
        url = f"{OLD_BASE_URL}/r/{subreddit}/{sort}"
        if after:
            url += f"?after={after}&count={len(collected)}"

        page = _load_page(context, url)
        if not page:
            break

        try:
            # Each post is a div with class "thing"
            things = page.query_selector_all("div.thing[data-fullname^='t3_']")
            if not things:
                logger.debug(f"No posts found on page for r/{subreddit}")
                page.close()
                break

            for thing in things:
                if len(collected) >= limit:
                    break
                try:
                    post = _extract_post_from_thing(thing, subreddit)
                    if post:
                        collected.append(post)
                except Exception as e:
                    logger.debug(f"Error extracting post: {e}")

            # Get "next" link for pagination
            next_btn = page.query_selector("a[rel='nofollow next']")
            if next_btn and len(collected) < limit:
                href = next_btn.get_attribute("href") or ""
                after_match = re.search(r"after=(t3_\w+)", href)
                after = after_match.group(1) if after_match else None
                if not after:
                    page.close()
                    break
            else:
                page.close()
                break

        except Exception as e:
            logger.debug(f"Page parse error: {e}")
            page.close()
            break

        page.close()
        time.sleep(2)

    return collected


def _extract_post_from_thing(thing, subreddit: str) -> Optional[dict]:
    def attr(sel, attribute):
        el = thing.query_selector(sel)
        return el.get_attribute(attribute) if el else ""

    def text(sel):
        el = thing.query_selector(sel)
        return el.inner_text().strip() if el else ""

    post_id = (thing.get_attribute("data-fullname") or "").replace("t3_", "")
    if not post_id:
        return None

    title_el = thing.query_selector("a.title")
    title = title_el.inner_text().strip() if title_el else ""
    url = title_el.get_attribute("href") if title_el else ""
    if url and url.startswith("/"):
        url = f"{OLD_BASE_URL}{url}"

    permalink_el = thing.query_selector("a.comments")
    permalink = permalink_el.get_attribute("href") if permalink_el else ""
    if permalink and permalink.startswith("/"):
        permalink = f"{BASE_URL}{permalink}"
    elif permalink and "old.reddit.com" in permalink:
        permalink = permalink.replace("old.reddit.com", "www.reddit.com")

    score_str = thing.get_attribute("data-score") or "0"
    try:
        score = int(score_str)
    except ValueError:
        score = 0

    timestamp_str = thing.get_attribute("data-timestamp") or "0"
    created_utc = float(timestamp_str) / 1000 if timestamp_str != "0" else 0.0

    num_comments_str = text("a.comments")
    num_comments = 0
    m = re.search(r"(\d[\d,]*)\s+comment", num_comments_str)
    if m:
        num_comments = int(m.group(1).replace(",", ""))

    flair_el = thing.query_selector("span.flair")
    flair = flair_el.inner_text().strip() if flair_el else None

    domain = thing.get_attribute("data-domain") or ""
    is_self = thing.get_attribute("data-type") == "self"

    return {
        "id": post_id,
        "subreddit": subreddit,
        "title": title,
        "selftext": "",
        "url": url,
        "permalink": permalink,
        "created_utc": created_utc,
        "score": score,
        "upvote_ratio": 1.0,
        "num_comments": num_comments,
        "link_flair_text": flair,
        "is_self": is_self,
        "is_video": False,
        "domain": domain,
    }


def _get_comments_raw(
    context: BrowserContext,
    subreddit: str,
    post_id: str,
    post_permalink: str,
    max_comments: int,
) -> List[dict]:
    url = post_permalink.replace("www.reddit.com", "old.reddit.com")
    if "old.reddit.com" not in url:
        url = f"{OLD_BASE_URL}/r/{subreddit}/comments/{post_id}/"

    page = _load_page(context, url)
    if not page:
        return []

    comments = []
    try:
        things = page.query_selector_all("div.comment[data-fullname^='t1_']")
        for thing in things:
            if len(comments) >= max_comments:
                break
            try:
                c = _extract_comment(thing, post_id, subreddit)
                if c:
                    comments.append(c)
            except Exception as e:
                logger.debug(f"Comment extract error: {e}")
    except Exception as e:
        logger.debug(f"Comments page error: {e}")
    finally:
        page.close()

    return comments


def _extract_comment(thing, post_id: str, subreddit: str) -> Optional[dict]:
    comment_id = (thing.get_attribute("data-fullname") or "").replace("t1_", "")
    if not comment_id:
        return None

    body_el = thing.query_selector("div.md")
    body = body_el.inner_text().strip() if body_el else ""
    if body in ("[deleted]", "[removed]", ""):
        return None

    score_str = thing.get_attribute("data-score") or "0"
    try:
        score = int(score_str)
    except ValueError:
        score = 0

    depth_str = thing.get_attribute("data-depth") or "0"
    try:
        depth = int(depth_str)
    except ValueError:
        depth = 0

    permalink_el = thing.query_selector("a.bylink")
    permalink = permalink_el.get_attribute("href") if permalink_el else ""
    if permalink and "old.reddit.com" in permalink:
        permalink = permalink.replace("old.reddit.com", "www.reddit.com")

    time_el = thing.query_selector("time")
    created_utc = 0.0
    if time_el:
        ts = time_el.get_attribute("datetime") or ""
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            created_utc = dt.timestamp()
        except Exception:
            pass

    return {
        "id": comment_id,
        "post_id": post_id,
        "subreddit": subreddit,
        "body": body,
        "score": score,
        "created_utc": created_utc,
        "depth": depth,
        "permalink": permalink,
    }


def _build_post(raw: dict, matched_keywords: List[str], sort_mode: str) -> RedditPost:
    return RedditPost(
        post_id=raw.get("id", ""),
        subreddit=raw.get("subreddit", ""),
        title=raw.get("title", ""),
        selftext=clean_body(raw.get("selftext", "")),
        url=raw.get("url", ""),
        permalink=raw.get("permalink", ""),
        created_utc=raw.get("created_utc", 0),
        created_date=utc_timestamp_to_date(raw.get("created_utc", 0)),
        score=raw.get("score", 0),
        upvote_ratio=raw.get("upvote_ratio", 1.0),
        num_comments=raw.get("num_comments", 0),
        flair=raw.get("link_flair_text"),
        is_self=raw.get("is_self", False),
        is_video=raw.get("is_video", False),
        domain=raw.get("domain", ""),
        matched_keywords=", ".join(matched_keywords),
        sort_mode=sort_mode,
        collected_at=now_utc_str(),
    )


def _build_comment(raw: dict, post_title: str, keywords: List[str]) -> RedditComment:
    matched = comment_matches(raw.get("body", ""), keywords)
    return RedditComment(
        comment_id=raw.get("id", ""),
        post_id=raw.get("post_id", ""),
        subreddit=raw.get("subreddit", ""),
        post_title=post_title,
        body=clean_body(raw.get("body", "")),
        score=raw.get("score", 0),
        created_utc=raw.get("created_utc", 0),
        created_date=utc_timestamp_to_date(raw.get("created_utc", 0)),
        depth=raw.get("depth", 0),
        permalink=raw.get("permalink", ""),
        matched_keywords=", ".join(matched),
        collected_at=now_utc_str(),
    )


def parse_subreddits(
    reddit: dict,
    subreddits: List[str],
    keywords: List[str],
    period: str,
    sort: str,
    limit: int,
    max_comments: int,
    min_score: int,
    min_comments: int,
) -> tuple[List[RedditPost], List[RedditComment]]:
    context = reddit["context"]
    all_posts: List[RedditPost] = []
    all_comments: List[RedditComment] = []
    cutoff = get_cutoff_timestamp(period)

    for subreddit_name in subreddits:
        logger.info(f"Fetching r/{subreddit_name} [{sort}, limit={limit}]")
        raw_posts = _get_posts_raw(context, subreddit_name, sort, limit)
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
                    context, subreddit_name, raw["id"], raw.get("permalink", ""), max_comments
                )
                for rc in raw_comments:
                    comment = _build_comment(rc, raw.get("title", ""), keywords)
                    all_comments.append(comment)
                if raw_comments:
                    logger.debug(f"  └─ {len(raw_comments)} comments for '{raw.get('title','')[:60]}'")
                time.sleep(1)

        logger.info(f"r/{subreddit_name}: {matched_count} posts matched filters")

    return all_posts, all_comments
