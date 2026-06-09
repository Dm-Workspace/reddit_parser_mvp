"""
Reddit client factory.

REDDIT_ACCESS_MODE controls which backend is used:

  public_json  (default)
    Scrape public Reddit JSON endpoints via requests.
    Requires: REDDIT_USER_AGENT
    Does NOT require: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

  playwright
    Scrape old.reddit.com HTML via headless Chromium.
    Requires: playwright installed  (playwright install chromium)
    Does NOT require: Reddit API credentials

  oauth
    Use PRAW + Reddit OAuth.
    Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

  auto
    If REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET set → oauth
    Otherwise → public_json

Default: public_json
"""
import os
import time
import re
from typing import List, Optional

from loguru import logger

# ── ENV ────────────────────────────────────────────────────────────────────────

REDDIT_ACCESS_MODE = os.environ.get("REDDIT_ACCESS_MODE", "public_json").lower()
REDDIT_USER_AGENT  = os.environ.get("REDDIT_USER_AGENT", "TrendIntelligenceHub/1.0")
REDDIT_CLIENT_ID   = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

BASE_URL     = "https://www.reddit.com"
OLD_BASE_URL = "https://old.reddit.com"


# ── Shared helpers (used by both clients) ─────────────────────────────────────

def get_effective_mode() -> str:
    """Resolve 'auto' to the actual mode that will be used."""
    mode = REDDIT_ACCESS_MODE
    if mode == "auto":
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            return "oauth"
        return "public_json"
    return mode


def get_reddit_status() -> dict:
    """Return a status dict for /status and --reddit-check."""
    mode = get_effective_mode()
    ua_ok = bool(REDDIT_USER_AGENT)
    creds_ok = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)
    return {
        "access_mode":          REDDIT_ACCESS_MODE,
        "effective_mode":       mode,
        "user_agent_set":       ua_ok,
        "credentials_set":      creds_ok,
    }


# ── Public JSON Client (requests-based, no OAuth needed) ──────────────────────

class PublicJsonClient:
    """
    Hits Reddit's public JSON endpoints (no OAuth).
    Rate-limit friendly: sleeps between requests.
    """

    def __init__(self, user_agent: str = REDDIT_USER_AGENT):
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests not installed — run: pip install requests")
        self._ua      = user_agent or "TrendIntelligenceHub/1.0"
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._ua})
        logger.info(f"[Reddit] PublicJsonClient created (no OAuth needed)")

    def _get_json(self, url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
        import requests
        for attempt in range(retries):
            try:
                r = self._session.get(url, params=params, timeout=20)
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", "30"))
                    logger.warning(f"[Reddit] Rate limited, sleeping {wait}s")
                    time.sleep(wait)
                    continue
                if r.status_code == 200:
                    return r.json()
                logger.debug(f"[Reddit] HTTP {r.status_code} for {url}")
                return None
            except Exception as e:
                logger.debug(f"[Reddit] request error (attempt {attempt+1}): {e}")
                if attempt < retries - 1:
                    time.sleep(3)
        return None

    def get_posts_raw(self, subreddit: str, sort: str, limit: int,
                      period: str = "") -> List[dict]:
        """
        Fetch posts from r/{subreddit}/{sort}.json
        period maps to Reddit 't' param: last_7d→week, last_24h→day, etc.
        """
        _PERIOD_MAP = {
            "last_24h": "day", "last_7d": "week",
            "last_30d": "month", "last_year": "year", "all_time": "all",
        }
        posts: List[dict] = []
        after: Optional[str] = None
        per_page = min(limit, 100)

        while len(posts) < limit:
            url = f"{BASE_URL}/r/{subreddit}/{sort}.json"
            params: dict = {"limit": per_page, "raw_json": 1}
            if after:
                params["after"] = after
            t_val = _PERIOD_MAP.get(period, "")
            if t_val and sort in ("top", "controversial"):
                params["t"] = t_val

            data = self._get_json(url, params)
            if not data:
                break

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                if len(posts) >= limit:
                    break
                p = child.get("data", {})
                posts.append(self._normalise_post(p, subreddit))

            after = data.get("data", {}).get("after")
            if not after or len(posts) >= limit:
                break

            time.sleep(1.5)

        logger.debug(f"[Reddit] r/{subreddit}/{sort}: {len(posts)} posts fetched")
        return posts

    @staticmethod
    def _normalise_post(p: dict, subreddit: str) -> dict:
        """Convert raw Reddit JSON post to the dict format reddit_parser.py expects."""
        post_id  = p.get("id", "")
        title    = p.get("title", "")
        selftext = p.get("selftext", "")
        if selftext in ("[deleted]", "[removed]"):
            selftext = ""
        url       = p.get("url", "")
        permalink = p.get("permalink", "")
        if permalink and not permalink.startswith("http"):
            permalink = BASE_URL + permalink
        return {
            "id":              post_id,
            "subreddit":       p.get("subreddit", subreddit),
            "title":           title,
            "selftext":        selftext,
            "url":             url,
            "permalink":       permalink,
            "created_utc":     float(p.get("created_utc", 0)),
            "score":           int(p.get("score", 0)),
            "upvote_ratio":    float(p.get("upvote_ratio", 1.0)),
            "num_comments":    int(p.get("num_comments", 0)),
            "link_flair_text": p.get("link_flair_text"),
            "is_self":         bool(p.get("is_self", False)),
            "is_video":        bool(p.get("is_video", False)),
            "domain":          p.get("domain", ""),
            "author":          p.get("author", ""),
        }

    def fetch_selftext(self, permalink: str) -> str:
        """Return selftext for a self post. Already included in get_posts_raw; this is a no-op."""
        # Public JSON already includes selftext in listing; no extra call needed.
        return ""

    def get_comments_raw(
        self,
        subreddit: str,
        post_id: str,
        post_permalink: str,
        max_comments: int,
    ) -> List[dict]:
        """
        Fetch comments for a post using /comments/{post_id}.json
        Returns up to max_comments flattened top-level + nested comments.
        """
        url  = f"{BASE_URL}/r/{subreddit}/comments/{post_id}.json"
        data = self._get_json(url, {"limit": max_comments, "depth": 5, "raw_json": 1})
        if not data or not isinstance(data, list) or len(data) < 2:
            return []

        comments: List[dict] = []
        self._flatten_comments(data[1].get("data", {}).get("children", []),
                               post_id, subreddit, comments, max_comments, depth=0)
        time.sleep(1.0)
        return comments

    def _flatten_comments(self, children: list, post_id: str, subreddit: str,
                          out: list, max_cnt: int, depth: int) -> None:
        for child in children:
            if len(out) >= max_cnt:
                break
            if child.get("kind") != "t1":
                continue
            d = child.get("data", {})
            body = d.get("body", "")
            if body in ("[deleted]", "[removed]", ""):
                continue
            author = d.get("author", "")
            score  = d.get("score")
            if isinstance(score, bool) or score is None:
                score = None
            permalink = d.get("permalink", "")
            if permalink and not permalink.startswith("http"):
                permalink = BASE_URL + permalink
            out.append({
                "id":            d.get("id", ""),
                "post_id":       post_id,
                "subreddit":     subreddit,
                "author":        author,
                "body":          body,
                "score":         score,
                "score_available": score is not None,
                "created_utc":   float(d.get("created_utc", 0)),
                "depth":         depth,
                "permalink":     permalink,
            })
            replies = d.get("replies", {})
            if isinstance(replies, dict):
                self._flatten_comments(
                    replies.get("data", {}).get("children", []),
                    post_id, subreddit, out, max_cnt, depth + 1,
                )

    def test_connection(self, subreddit: str = "Supplements") -> dict:
        """
        Make a real HTTP request and return diagnostic info.
        Returns: {test_url, http_status, children_count, sample_titles, error}
        """
        import requests
        url = f"{BASE_URL}/r/{subreddit}/hot.json"
        params = {"limit": 5, "raw_json": 1}
        try:
            r = self._session.get(url, params=params, timeout=20)
            http_status = r.status_code
            if r.status_code == 200:
                data = r.json()
                children = data.get("data", {}).get("children", [])
                titles = [c["data"].get("title", "")[:70]
                          for c in children if c.get("data")]
                return {
                    "test_url":       url,
                    "http_status":    http_status,
                    "children_count": len(children),
                    "sample_titles":  titles,
                    "error":          None,
                }
            else:
                return {
                    "test_url":       url,
                    "http_status":    http_status,
                    "children_count": 0,
                    "sample_titles":  [],
                    "error":          f"HTTP {http_status}",
                }
        except Exception as e:
            return {
                "test_url":       url,
                "http_status":    None,
                "children_count": 0,
                "sample_titles":  [],
                "error":          str(e),
            }

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass


# ── Playwright Client (headless browser, no OAuth needed) ─────────────────────

class PlaywrightClient:
    """
    Wraps the original Playwright HTML scraper.
    Requires playwright + chromium installed.
    No Reddit API credentials needed.
    """

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        self._ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        self._ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        # Expose playwright context for legacy parse code
        self.context = self._ctx
        logger.info("[Reddit] PlaywrightClient created (headless browser, no OAuth)")

    def get_posts_raw(self, subreddit: str, sort: str, limit: int,
                      period: str = "") -> List[dict]:
        from reddit_parser import _get_posts_raw
        return _get_posts_raw(self._ctx, subreddit, sort, limit)

    def fetch_selftext(self, permalink: str) -> str:
        from reddit_parser import _fetch_selftext
        return _fetch_selftext(self._ctx, permalink)

    def get_comments_raw(self, subreddit: str, post_id: str,
                         post_permalink: str, max_comments: int) -> List[dict]:
        from reddit_parser import _get_comments_raw
        return _get_comments_raw(self._ctx, subreddit, post_id, post_permalink, max_comments)

    def test_connection(self, subreddit: str = "Supplements") -> dict:
        """Playwright doesn't expose raw HTTP; return a not-supported stub."""
        return {
            "test_url":       f"https://old.reddit.com/r/{subreddit}/hot",
            "http_status":    None,
            "children_count": None,
            "sample_titles":  [],
            "error":          "http_check_not_supported_for_playwright",
        }

    def close(self) -> None:
        try:
            self._ctx.close()
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


# ── PRAW / OAuth client stub ───────────────────────────────────────────────────

class PrawClient:
    """
    PRAW-based Reddit client (OAuth). Optional — only for REDDIT_ACCESS_MODE=oauth.
    Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    """

    def __init__(self):
        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            raise RuntimeError(
                "REDDIT_ACCESS_MODE=oauth requires REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET to be set."
            )
        if not REDDIT_USER_AGENT:
            raise RuntimeError("REDDIT_USER_AGENT must be set for oauth mode.")
        try:
            import praw
        except ImportError:
            raise RuntimeError("praw not installed — run: pip install praw")
        self._reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            read_only=True,
        )
        logger.info("[Reddit] PrawClient created (OAuth)")

    def get_posts_raw(self, subreddit: str, sort: str, limit: int,
                      period: str = "") -> List[dict]:
        _PERIOD_MAP = {
            "last_24h": "day", "last_7d": "week",
            "last_30d": "month", "last_year": "year", "all_time": "all",
        }
        sub  = self._reddit.subreddit(subreddit)
        func = getattr(sub, sort, sub.hot)
        t    = _PERIOD_MAP.get(period, "week")
        try:
            if sort in ("top", "controversial"):
                submissions = list(func(limit=limit, time_filter=t))
            else:
                submissions = list(func(limit=limit))
        except Exception as e:
            logger.warning(f"[PRAW] r/{subreddit}: {e}")
            return []
        return [self._normalise(s) for s in submissions]

    @staticmethod
    def _normalise(s) -> dict:
        return {
            "id":              s.id,
            "subreddit":       str(s.subreddit),
            "title":           s.title,
            "selftext":        s.selftext if s.selftext not in ("[deleted]", "[removed]") else "",
            "url":             s.url,
            "permalink":       BASE_URL + s.permalink,
            "created_utc":     float(s.created_utc),
            "score":           int(s.score),
            "upvote_ratio":    float(s.upvote_ratio),
            "num_comments":    int(s.num_comments),
            "link_flair_text": s.link_flair_text,
            "is_self":         bool(s.is_self),
            "is_video":        bool(s.is_video),
            "domain":          s.domain,
            "author":          str(s.author) if s.author else "",
        }

    def fetch_selftext(self, permalink: str) -> str:
        return ""   # selftext already included in get_posts_raw

    def get_comments_raw(self, subreddit: str, post_id: str,
                         post_permalink: str, max_comments: int) -> List[dict]:
        try:
            submission = self._reddit.submission(id=post_id)
            submission.comments.replace_more(limit=0)
            out = []
            for c in submission.comments.list()[:max_comments]:
                if c.body in ("[deleted]", "[removed]"):
                    continue
                out.append({
                    "id":            c.id,
                    "post_id":       post_id,
                    "subreddit":     subreddit,
                    "author":        str(c.author) if c.author else "",
                    "body":          c.body,
                    "score":         c.score,
                    "score_available": True,
                    "created_utc":   float(c.created_utc),
                    "depth":         c.depth,
                    "permalink":     BASE_URL + c.permalink,
                })
            return out
        except Exception as e:
            logger.warning(f"[PRAW] comments for {post_id}: {e}")
            return []

    def test_connection(self, subreddit: str = "Supplements") -> dict:
        """PRAW doesn't give raw HTTP info; return a not-supported stub."""
        return {
            "test_url":       f"https://oauth.reddit.com/r/{subreddit}/hot",
            "http_status":    None,
            "children_count": None,
            "sample_titles":  [],
            "error":          "http_check_not_supported_for_praw",
        }

    def close(self) -> None:
        pass


# ── Factory functions (public API) ─────────────────────────────────────────────

def create_reddit_client():
    """
    Return the appropriate Reddit client based on REDDIT_ACCESS_MODE.
    - public_json  → PublicJsonClient  (default, no OAuth needed)
    - playwright   → PlaywrightClient  (legacy, no OAuth needed)
    - oauth        → PrawClient        (requires credentials)
    - auto         → oauth if creds present, else public_json
    """
    mode = REDDIT_ACCESS_MODE

    if mode == "public_json":
        if not REDDIT_USER_AGENT:
            raise RuntimeError(
                "REDDIT_USER_AGENT must be set (e.g. 'TrendIntelligenceHub/1.0').\n"
                "Add it to your .env file."
            )
        return PublicJsonClient(user_agent=REDDIT_USER_AGENT)

    if mode == "playwright":
        return PlaywrightClient()

    if mode == "oauth":
        return PrawClient()

    if mode == "auto":
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            logger.info("[Reddit] auto mode: credentials found → using oauth")
            return PrawClient()
        logger.info("[Reddit] auto mode: no credentials → using public_json")
        return PublicJsonClient(user_agent=REDDIT_USER_AGENT)

    # Unknown mode — fall back to public_json
    logger.warning(f"[Reddit] Unknown REDDIT_ACCESS_MODE={mode!r}, falling back to public_json")
    return PublicJsonClient(user_agent=REDDIT_USER_AGENT)


def close_reddit_client(client) -> None:
    """Close any resources held by the client."""
    try:
        client.close()
    except Exception:
        pass
