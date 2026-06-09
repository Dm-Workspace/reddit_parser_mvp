"""
Reddit client factory.

REDDIT_ACCESS_MODE controls which backend is used:

  playwright   (DEFAULT)
    Headless Chromium scraping via Playwright.
    Scrapes old.reddit.com HTML listings + comments.
    Does NOT require REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET.
    Requires: playwright + chromium installed.

  requests_json  (alias: public_json)
    requests-based client hitting reddit.com/{sort}.json endpoints.
    Does NOT require credentials, but may be blocked by Reddit (HTTP 403).
    Use only when Playwright is unavailable or for quick debug tests.

  oauth
    PRAW + Reddit OAuth.
    Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT.

  auto
    Order: oauth (if creds) → playwright → requests_json
    Tries playwright, falls back to requests_json on launch failure.

Default: playwright
"""
import os
import time
import re
from typing import List, Optional

from loguru import logger

# ── ENV ────────────────────────────────────────────────────────────────────────

REDDIT_ACCESS_MODE   = os.environ.get("REDDIT_ACCESS_MODE", "playwright").lower()
REDDIT_USER_AGENT    = os.environ.get("REDDIT_USER_AGENT", "TrendIntelligenceHub/1.0")
REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

BASE_URL     = "https://www.reddit.com"
OLD_BASE_URL = "https://old.reddit.com"

# Normalise legacy mode name
_MODE_ALIASES = {"public_json": "requests_json"}


def _normalise_mode(mode: str) -> str:
    return _MODE_ALIASES.get(mode, mode)


# ── Shared helpers ────────────────────────────────────────────────────────────

def get_effective_mode() -> str:
    """Resolve 'auto' and aliases to the actual mode that will be used."""
    mode = _normalise_mode(REDDIT_ACCESS_MODE)
    if mode == "auto":
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            return "oauth"
        return "playwright"
    return mode


def get_reddit_status() -> dict:
    """Return a summary dict for /status and --reddit-check."""
    mode    = get_effective_mode()
    ua_ok   = bool(REDDIT_USER_AGENT)
    creds   = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)
    return {
        "access_mode":     _normalise_mode(REDDIT_ACCESS_MODE),
        "effective_mode":  mode,
        "user_agent_set":  ua_ok,
        "credentials_set": creds,
    }


# ── Custom exception ──────────────────────────────────────────────────────────

class RedditAccessError(RuntimeError):
    """Raised when Reddit returns a non-200 HTTP status."""
    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(
            f"Reddit returned HTTP {status_code} for {url}. "
            + ({
                403: "Access blocked (403). Reddit is blocking this IP/User-Agent. "
                     "Switch to REDDIT_ACCESS_MODE=playwright.",
                429: "Rate limited (429). Wait a few minutes before retrying.",
            }.get(status_code, ""))
        )


# ── Playwright Client — headless browser, NO credentials needed ───────────────

class PlaywrightClient:
    """
    Scrapes old.reddit.com via headless Chromium.
    Primary production backend — no Reddit API credentials needed.
    """

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
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
        self.context = self._ctx          # expose for legacy callers
        logger.info("[Reddit] PlaywrightClient started (headless browser, no OAuth)")

    # ── Core interface ────────────────────────────────────────────────────────

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
        return _get_comments_raw(self._ctx, subreddit, post_id, post_permalink,
                                 max_comments)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def test_connection(self, subreddit: str = "Supplements") -> dict:
        """
        Open old.reddit.com/{subreddit}/hot, extract up to 3 posts.
        Returns: {test_url, playwright_available, browser_launch, children_count,
                  sample_titles, error}
        """
        test_url = f"{OLD_BASE_URL}/r/{subreddit}/hot"
        base = {
            "test_url":            test_url,
            "playwright_available": True,
            "browser_launch":       "ok",
        }
        try:
            posts = self.get_posts_raw(subreddit, "hot", 3)
            return {
                **base,
                "children_count": len(posts),
                "sample_titles":  [p.get("title", "")[:70] for p in posts[:3]],
                "error":          None if posts else "browser opened but 0 posts extracted",
            }
        except Exception as e:
            return {
                **base,
                "children_count": 0,
                "sample_titles":  [],
                "error":          str(e),
            }

    def close(self) -> None:
        try:
            self._ctx.close()
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


# ── Requests JSON Client — direct API, may be blocked by Reddit ───────────────

class RequestsJsonClient:
    """
    Hits Reddit's public JSON endpoints via requests.
    Quick and lightweight, but Reddit may return HTTP 403 on cloud IPs.
    Use REDDIT_ACCESS_MODE=playwright for reliable production access.
    """

    def __init__(self, user_agent: str = REDDIT_USER_AGENT):
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests not installed — run: pip install requests")
        self._ua      = user_agent or "TrendIntelligenceHub/1.0"
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._ua})
        self._last_http_status: Optional[int] = None
        logger.info("[Reddit] RequestsJsonClient created (no OAuth needed)")

    def _get_json(self, url: str, params: dict = None,
                  retries: int = 3) -> Optional[dict]:
        for attempt in range(retries):
            try:
                r = self._session.get(url, params=params, timeout=20)
                self._last_http_status = r.status_code
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", "30"))
                    logger.warning(f"[Reddit] Rate limited (429), sleeping {wait}s")
                    time.sleep(wait)
                    continue
                if r.status_code == 403:
                    raise RedditAccessError(403, url)
                if r.status_code == 200:
                    return r.json()
                logger.warning(f"[Reddit] HTTP {r.status_code} for {url}")
                return None
            except RedditAccessError:
                raise
            except Exception as e:
                logger.debug(f"[Reddit] request error (attempt {attempt+1}): {e}")
                if attempt < retries - 1:
                    time.sleep(3)
        return None

    def get_posts_raw(self, subreddit: str, sort: str, limit: int,
                      period: str = "") -> List[dict]:
        _PERIOD_MAP = {
            "last_24h": "day", "last_7d": "week",
            "last_30d": "month", "last_year": "year", "all_time": "all",
        }
        posts: List[dict] = []
        after: Optional[str] = None
        per_page = min(limit, 100)

        while len(posts) < limit:
            url    = f"{BASE_URL}/r/{subreddit}/{sort}.json"
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
        post_id  = p.get("id", "")
        selftext = p.get("selftext", "")
        if selftext in ("[deleted]", "[removed]"):
            selftext = ""
        permalink = p.get("permalink", "")
        if permalink and not permalink.startswith("http"):
            permalink = BASE_URL + permalink
        return {
            "id":              post_id,
            "subreddit":       p.get("subreddit", subreddit),
            "title":           p.get("title", ""),
            "selftext":        selftext,
            "url":             p.get("url", ""),
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
        """Selftext already included in listing; no extra call needed."""
        return ""

    def get_comments_raw(self, subreddit: str, post_id: str,
                         post_permalink: str, max_comments: int) -> List[dict]:
        url  = f"{BASE_URL}/r/{subreddit}/comments/{post_id}.json"
        data = self._get_json(url, {"limit": max_comments, "depth": 5, "raw_json": 1})
        if not data or not isinstance(data, list) or len(data) < 2:
            return []
        comments: List[dict] = []
        self._flatten_comments(
            data[1].get("data", {}).get("children", []),
            post_id, subreddit, comments, max_comments, depth=0,
        )
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
            score = d.get("score")
            if isinstance(score, bool) or score is None:
                score = None
            permalink = d.get("permalink", "")
            if permalink and not permalink.startswith("http"):
                permalink = BASE_URL + permalink
            out.append({
                "id":            d.get("id", ""),
                "post_id":       post_id,
                "subreddit":     subreddit,
                "author":        d.get("author", ""),
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
        """Make a real HTTP request and return diagnostic info."""
        url    = f"{BASE_URL}/r/{subreddit}/hot.json"
        params = {"limit": 5, "raw_json": 1}
        base   = {
            "test_url":            url,
            "playwright_available": False,
            "browser_launch":      "n/a",
        }
        try:
            import requests
            r = self._session.get(url, params=params, timeout=20)
            self._last_http_status = r.status_code
            if r.status_code == 200:
                data     = r.json()
                children = data.get("data", {}).get("children", [])
                titles   = [c["data"].get("title", "")[:70]
                            for c in children if c.get("data")]
                return {
                    **base,
                    "http_status":    r.status_code,
                    "children_count": len(children),
                    "sample_titles":  titles,
                    "error":          None,
                }
            else:
                return {
                    **base,
                    "http_status":    r.status_code,
                    "children_count": 0,
                    "sample_titles":  [],
                    "error":          f"HTTP {r.status_code}",
                }
        except Exception as e:
            return {
                **base,
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


# Backward-compat alias
PublicJsonClient = RequestsJsonClient


# ── PRAW / OAuth client ────────────────────────────────────────────────────────

class PrawClient:
    """
    PRAW-based Reddit client (OAuth). Optional — only for REDDIT_ACCESS_MODE=oauth.
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
        return ""

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
        return {
            "test_url":            f"https://oauth.reddit.com/r/{subreddit}/hot",
            "playwright_available": False,
            "browser_launch":      "n/a",
            "http_status":         None,
            "children_count":      None,
            "sample_titles":       [],
            "error":               "http_check_not_supported_for_praw",
        }

    def close(self) -> None:
        pass


# ── Factory functions ─────────────────────────────────────────────────────────

def _playwright_available() -> bool:
    """Check if playwright package is installed (not whether browser is launched)."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def create_reddit_client():
    """
    Return the appropriate Reddit client based on REDDIT_ACCESS_MODE.

    playwright      → PlaywrightClient  (default, no credentials)
    requests_json   → RequestsJsonClient (no credentials, may be blocked)
    public_json     → RequestsJsonClient (alias for requests_json)
    oauth           → PrawClient        (requires REDDIT_CLIENT_ID/SECRET)
    auto            → oauth if creds; else playwright
    """
    mode = _normalise_mode(REDDIT_ACCESS_MODE)

    if mode == "playwright":
        return PlaywrightClient()

    if mode == "requests_json":
        if not REDDIT_USER_AGENT:
            raise RuntimeError(
                "REDDIT_USER_AGENT must be set (e.g. 'TrendIntelligenceHub/1.0')."
            )
        return RequestsJsonClient(user_agent=REDDIT_USER_AGENT)

    if mode == "oauth":
        return PrawClient()

    if mode == "auto":
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            logger.info("[Reddit] auto mode: credentials found → using oauth")
            return PrawClient()
        logger.info("[Reddit] auto mode: no credentials → using playwright")
        return PlaywrightClient()

    # Unknown mode — fall back to playwright
    logger.warning(
        f"[Reddit] Unknown REDDIT_ACCESS_MODE={mode!r}, falling back to playwright"
    )
    return PlaywrightClient()


def close_reddit_client(client) -> None:
    """Close any resources held by the client."""
    try:
        client.close()
    except Exception:
        pass
