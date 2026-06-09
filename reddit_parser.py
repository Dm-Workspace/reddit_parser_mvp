import time
import re
from typing import List, Optional
from loguru import logger
from playwright.sync_api import BrowserContext, Page

from reddit_models import (
    RedditPost, RedditComment,
    COMMENT_MATCH_DIRECT, COMMENT_MATCH_CONTEXT, COMMENT_MATCH_NONE,
    detect_content_type, compute_analysis_priority, detect_pain_signal, detect_text_status,
)
from reddit_filters import post_matches_data, comment_matches, is_bot_comment
from utils.date_utils import utc_timestamp_to_date, now_utc_str, get_cutoff_timestamp
from utils.text_cleaner import clean_body
from utils.language_utils import detect_language, passes_language_filter

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


def _compute_trend_score(score: int, num_comments: int) -> float:
    return round(score + num_comments * 2.0, 2)


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

    num_comments_str = ""
    comments_el = thing.query_selector("a.comments")
    if comments_el:
        num_comments_str = comments_el.inner_text().strip()
    num_comments = 0
    m = re.search(r"(\d[\d,]*)\s+comment", num_comments_str)
    if m:
        num_comments = int(m.group(1).replace(",", ""))

    flair_el = thing.query_selector("span.flair")
    flair = flair_el.inner_text().strip() if flair_el else None

    domain = thing.get_attribute("data-domain") or ""
    is_self = domain.startswith("self.")

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


def _fetch_selftext(context: BrowserContext, permalink: str) -> str:
    old_url = permalink.replace("www.reddit.com", "old.reddit.com")
    page = _load_page(context, old_url)
    if not page:
        return ""
    try:
        el = page.query_selector("div.thing div.usertext-body div.md")
        if el:
            return clean_body(el.inner_text().strip())
        return ""
    except Exception as e:
        logger.debug(f"selftext fetch error: {e}")
        return ""
    finally:
        page.close()


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

    author = thing.get_attribute("data-author") or ""

    raw_score = thing.get_attribute("data-score")
    score_available = raw_score is not None and raw_score.strip() not in ("", "—", "null", "hidden")
    try:
        score = int(raw_score) if score_available else None
    except (ValueError, TypeError):
        score = None
        score_available = False

    depth_str = thing.get_attribute("data-depth") or "0"
    try:
        depth = int(depth_str)
    except ValueError:
        depth = 0

    permalink_el = thing.query_selector("a.bylink")
    permalink = permalink_el.get_attribute("href") if permalink_el else ""
    if permalink and "old.reddit.com" in permalink:
        permalink = permalink.replace("old.reddit.com", "www.reddit.com")

    created_utc = 0.0
    time_el = thing.query_selector("time")
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
        "author": author,
        "body": body,
        "score": score,
        "score_available": score_available,
        "created_utc": created_utc,
        "depth": depth,
        "permalink": permalink,
    }


def _build_post(raw: dict, matched_keywords: List[str], sort_mode: str) -> RedditPost:
    selftext = raw.get("selftext", "")
    title = raw.get("title", "")
    lang = detect_language(f"{title} {selftext}")
    trend = _compute_trend_score(raw.get("score", 0), raw.get("num_comments", 0))
    num_comments = raw.get("num_comments", 0)
    return RedditPost(
        post_id=raw.get("id", ""),
        subreddit=raw.get("subreddit", ""),
        title=title,
        selftext=selftext,
        url=raw.get("url", ""),
        permalink=raw.get("permalink", ""),
        created_utc=raw.get("created_utc", 0),
        created_date=utc_timestamp_to_date(raw.get("created_utc", 0)),
        score=raw.get("score", 0),
        upvote_ratio=raw.get("upvote_ratio", 1.0),
        num_comments=num_comments,
        flair=raw.get("link_flair_text"),
        is_self=raw.get("is_self", False),
        is_video=raw.get("is_video", False),
        domain=raw.get("domain", ""),
        matched_keywords=", ".join(matched_keywords),
        sort_mode=sort_mode,
        collected_at=now_utc_str(),
        post_text_length=len(selftext),
        language_detected=lang,
        trend_score=trend,
        content_type=detect_content_type(raw),
        analysis_priority=compute_analysis_priority(trend, num_comments),
        pain_signal=detect_pain_signal(title, selftext),
        text_status=detect_text_status(selftext, detect_content_type(raw)),
    )


def _build_comment(
    raw: dict,
    post_title: str,
    keywords: List[str],
    post_has_keywords: bool,
    min_comment_length: int,
) -> Optional[RedditComment]:
    body = clean_body(raw.get("body", ""))
    score = raw.get("score")  # may be None if hidden
    score_available = raw.get("score_available", False)
    score_for_filter = score if score is not None else 0

    # Filter short low-value comments (unless high score)
    if len(body) < min_comment_length and score_for_filter <= 10:
        return None

    author = raw.get("author", "")
    matched = comment_matches(body, keywords)
    lang = detect_language(body)
    bot = is_bot_comment(author, body)

    if matched:
        match_type = COMMENT_MATCH_DIRECT
    elif post_has_keywords:
        match_type = COMMENT_MATCH_CONTEXT
    else:
        match_type = COMMENT_MATCH_NONE

    return RedditComment(
        comment_id=raw.get("id", ""),
        post_id=raw.get("post_id", ""),
        subreddit=raw.get("subreddit", ""),
        post_title=post_title,
        author=author,
        body=body,
        score=score,
        created_utc=raw.get("created_utc", 0),
        created_date=utc_timestamp_to_date(raw.get("created_utc", 0)),
        depth=raw.get("depth", 0),
        permalink=raw.get("permalink", ""),
        matched_keywords=", ".join(matched),
        collected_at=now_utc_str(),
        comment_text_length=len(body),
        language_detected=lang,
        is_bot_comment=bot,
        comment_match_type=match_type,
        comment_score_available=score_available,
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
    fetch_selftext: bool = True,
    filter_bots: bool = True,
    language_mode: str = "mixed",
    min_comment_length: int = 40,
) -> tuple[List[RedditPost], List[RedditComment]]:
    context = reddit["context"]
    all_posts: List[RedditPost] = []
    all_comments: List[RedditComment] = []
    cutoff = get_cutoff_timestamp(period)

    for subreddit_name in subreddits:
        logger.info(f"Fetching r/{subreddit_name} [{sort}, limit={limit}]")
        raw_posts = _get_posts_raw(context, subreddit_name, sort, limit)
        logger.info(f"r/{subreddit_name}: got {len(raw_posts)} raw posts")

        sub_matched = 0
        for raw in raw_posts:
            ok, matched_kws = post_matches_data(raw, keywords, cutoff, min_score, min_comments)
            if not ok:
                continue

            if fetch_selftext and raw.get("is_self") and raw.get("permalink"):
                logger.debug(f"Fetching selftext: '{raw.get('title', '')[:60]}'")
                raw["selftext"] = _fetch_selftext(context, raw["permalink"])
                time.sleep(0.8)

            post = _build_post(raw, matched_kws, sort)

            if not passes_language_filter(post.language_detected, language_mode):
                logger.debug(f"Skip post (lang={post.language_detected}): {post.title[:50]}")
                continue

            all_posts.append(post)
            sub_matched += 1
            post_has_keywords = bool(matched_kws)

            if max_comments > 0:
                raw_comments = _get_comments_raw(
                    context, subreddit_name, raw["id"], raw.get("permalink", ""), max_comments
                )
                added = 0
                for rc in raw_comments:
                    if filter_bots and is_bot_comment(rc.get("author", ""), rc.get("body", "")):
                        logger.debug(f"Bot comment filtered: {rc.get('author')}")
                        continue
                    comment = _build_comment(
                        rc, raw.get("title", ""), keywords, post_has_keywords, min_comment_length
                    )
                    if comment is None:
                        continue
                    if not passes_language_filter(comment.language_detected, language_mode):
                        continue
                    all_comments.append(comment)
                    added += 1

                if added:
                    logger.debug(f"  └─ {added} comments for '{raw.get('title','')[:55]}'")
                time.sleep(1)

        logger.info(f"r/{subreddit_name}: {sub_matched} posts matched")

    return all_posts, all_comments
