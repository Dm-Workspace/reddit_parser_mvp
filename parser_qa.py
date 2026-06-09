"""
Parser QA / Smoke-test module.

Entry points:
  run_smoke_test(upload_drive=False) -> SmokeResult
      Checks that public_json client actually fetches posts.
      Uses keywords=[] so ALL posts pass keyword filter.
      0 posts / 0 comments → FAIL.

  run_keyword_test() -> SmokeResult
      Checks keyword-filtered parsing (magnesium/sleep/fatigue).
      0 posts → FAIL only if raw_posts_fetched > 0.
      May return WARNING if dataset is small.

  run_qa_file(xlsx_path) -> QAResult
      Static check of a finished export Excel. No network calls.

All three are called from main_runner.py CLI flags.
No Telegram, no Railway, no full DB needed.
"""
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict


# ── Constants ──────────────────────────────────────────────────────────────────

# smoke-test: NO keyword filter — tests raw collection
SMOKE_SUBREDDITS   = ["Supplements", "Biohackers"]
SMOKE_KEYWORDS     = []          # intentionally empty — all posts pass
SMOKE_PERIOD       = "last_7d"
SMOKE_SORT         = "hot"
SMOKE_LIMIT        = 10          # posts per subreddit
SMOKE_COMMENTS     = 5           # comments per post
SMOKE_MIN_SCORE    = 0
SMOKE_MIN_COMMENTS = 0

# keyword-test: test keyword filtering with real keywords
KW_SUBREDDITS      = ["Supplements", "Biohackers"]
KW_KEYWORDS        = ["magnesium", "sleep", "fatigue"]
KW_PERIOD          = "last_7d"
KW_SORT            = "hot"
KW_LIMIT           = 50          # wider sweep to find keyword matches
KW_COMMENTS        = 5
KW_MIN_SCORE       = 0
KW_MIN_COMMENTS    = 0

REQUIRED_SHEETS = {"Posts", "Comments", "Summary"}
QA_PASS    = "PASS"
QA_WARNING = "WARNING"
QA_FAIL    = "FAIL"


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class SmokeResult:
    test_type: str                   = "smoke"   # "smoke" or "keyword"
    success: bool                    = False
    status: str                      = QA_FAIL   # PASS / WARNING / FAIL
    error: Optional[str]             = None
    posts_count: int                 = 0
    comments_count: int              = 0
    bot_comments_count: int          = 0
    empty_title_count: int           = 0
    empty_permalink_count: int       = 0
    empty_selftext_count: int        = 0
    duplicate_posts_removed: int     = 0
    top_keywords: List[dict]         = field(default_factory=list)
    warning_message: Optional[str]   = None
    # Debug counters (populated via _debug dict passed to parse_subreddits)
    raw_posts_fetched: int           = 0
    after_filter: int                = 0
    final_posts: int                 = 0
    comments_fetched: int            = 0
    # Export paths
    export_dir: str                  = ""
    xlsx_path: Optional[str]         = None
    json_path: Optional[str]         = None
    handoff_json_path: Optional[str] = None
    # Drive (only when --upload-drive)
    drive_xlsx_id: Optional[str]     = None
    drive_xlsx_link: Optional[str]   = None
    drive_upload_status: str         = "skipped"


@dataclass
class QAResult:
    status: str                              # PASS / WARNING / FAIL
    xlsx_path: str                           = ""
    sheets_found: List[str]                  = field(default_factory=list)
    missing_sheets: List[str]                = field(default_factory=list)
    total_posts: int                         = 0
    total_comments: int                      = 0
    top_posts_count: int                     = 0
    empty_titles: int                        = 0
    empty_permalinks: int                    = 0
    bot_comments_count: int                  = 0
    duplicated_post_ids: int                 = 0
    trend_score_zero_count: int              = 0
    empty_selftext_count: int                = 0
    pain_signal_distribution: Dict[str, int] = field(default_factory=dict)
    language_distribution: Dict[str, int]    = field(default_factory=dict)
    warnings: List[str]                      = field(default_factory=list)
    errors: List[str]                        = field(default_factory=list)


# ── Reddit ENV check ──────────────────────────────────────────────────────────

def _check_reddit_env() -> None:
    """
    Verify that the configured REDDIT_ACCESS_MODE can actually work.

    public_json / playwright / auto-without-creds:
        Only REDDIT_USER_AGENT is required (has a default).

    oauth / auto-with-creds:
        REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET required.
    """
    from reddit_client import get_effective_mode, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

    mode = get_effective_mode()
    if mode == "oauth":
        missing = []
        if not REDDIT_CLIENT_ID:
            missing.append("REDDIT_CLIENT_ID")
        if not REDDIT_CLIENT_SECRET:
            missing.append("REDDIT_CLIENT_SECRET")
        if missing:
            raise RuntimeError(
                f"REDDIT_ACCESS_MODE=oauth requires: {', '.join(missing)}\n"
                f"Either set those credentials OR switch to:\n"
                f"  REDDIT_ACCESS_MODE=public_json  (no credentials needed)"
            )
    # public_json / playwright / auto → user agent defaults, no credentials needed


# ── Shared parse helper ────────────────────────────────────────────────────────

def _run_parse(
    subreddits: List[str],
    keywords: List[str],
    period: str,
    sort: str,
    limit: int,
    max_comments: int,
    min_score: int,
    min_comments: int,
    debug: dict,
) -> tuple:
    """
    Create client, run parse_subreddits, close client.
    Returns (posts, comments) with debug counters populated.
    """
    from reddit_client import create_reddit_client, close_reddit_client
    from reddit_parser import parse_subreddits

    reddit = create_reddit_client()
    try:
        posts, comments = parse_subreddits(
            reddit=reddit,
            subreddits=subreddits,
            keywords=keywords,
            period=period,
            sort=sort,
            limit=limit,
            max_comments=max_comments,
            min_score=min_score,
            min_comments=min_comments,
            language_mode="mixed",
            _debug=debug,
        )
    finally:
        close_reddit_client(reddit)
    return posts, comments


def _build_exports(
    posts, comments, run_id: str, out_dir: str,
    subreddits: List[str], keywords: List[str],
    period: str, sort: str, limit: int, max_comments: int,
    ts: str,
) -> dict:
    """Build xlsx / json / handoff_json. Returns {xlsx_path, json_path, handoff_path}."""
    from exporters.excel_exporter import export_excel
    from exporters.json_exporter import export_json
    from exporters.handoff_exporter import export_handoff
    from storage.models import Run, Monitor, Project, RUN_COMPLETED

    run_settings = {
        "run_date":    ts,
        "run_id":      run_id,
        "monitor_id":  run_id,
        "monitor_name": run_id.replace("_", " ").title(),
        "project_id":  "smoke_test",
        "owner_telegram_id": "0",
        "subreddits":  ", ".join(subreddits),
        "subreddit_preset": "custom",
        "keywords":    ", ".join(keywords) if keywords else "(none)",
        "keyword_preset": "custom",
        "period":      period,
        "sort":        sort,
        "run_mode":    f"{sort}_{period}",
        "limit_per_subreddit":   limit,
        "max_comments_per_post": max_comments,
        "min_score":   0,
        "min_comments": 0,
        "language_mode": "mixed",
        "filter_bots": True,
        "fetch_selftext": True,
        "export_format": ["xlsx", "json"],
    }

    os.makedirs(out_dir, exist_ok=True)

    xlsx_path = os.path.join(out_dir, f"{run_id}.xlsx")
    export_excel(posts, comments, run_settings, xlsx_path, all_subreddits=subreddits)

    json_path = os.path.join(out_dir, f"{run_id}.json")
    export_json(posts, comments, run_settings, json_path)

    mock_run = Run(
        id=run_id, monitor_id=run_id, project_id="smoke_test",
        status=RUN_COMPLETED, started_at=ts,
        total_posts=len(posts), total_comments=len(comments),
    )
    mock_monitor = Monitor(
        id=run_id, project_id="smoke_test", name=run_id.replace("_", " ").title(),
        custom_subreddits=json.dumps(subreddits),
        custom_keywords=json.dumps(keywords),
        run_mode=f"{sort}_{period}",
    )
    mock_project = Project(
        id="smoke_test", name="Smoke Test",
        description="Parser QA smoke test run",
    )
    handoff_path = export_handoff(
        posts=posts, comments=comments,
        run=mock_run, monitor=mock_monitor, project=mock_project,
        run_settings=run_settings, output_dir=out_dir,
    )
    return {"xlsx_path": xlsx_path, "json_path": json_path, "handoff_path": handoff_path}


def _quality_metrics(posts, comments) -> dict:
    """Compute QA metrics on parsed posts/comments lists."""
    from utils.deduplication import deduplicate_posts, deduplicate_comments
    from collections import Counter

    pre_dedup = len(posts)
    posts_dd  = deduplicate_posts(posts)
    comments_dd = deduplicate_comments(comments)

    bot_cnt   = sum(1 for c in comments_dd if getattr(c, "is_bot_comment", False))
    empty_ttl = sum(1 for p in posts_dd if not (p.title or "").strip())
    empty_per = sum(1 for p in posts_dd if not (p.permalink or "").strip())
    empty_sel = sum(1 for p in posts_dd if not (p.selftext or "").strip())

    kw_counter: Counter = Counter()
    for p in posts_dd:
        for kw in (p.matched_keywords or "").split(", "):
            kw = kw.strip()
            if kw:
                kw_counter[kw] += 1

    return {
        "posts":           posts_dd,
        "comments":        comments_dd,
        "posts_count":     len(posts_dd),
        "comments_count":  len(comments_dd),
        "dup_removed":     pre_dedup - len(posts_dd),
        "bot_comments":    bot_cnt,
        "empty_title":     empty_ttl,
        "empty_permalink": empty_per,
        "empty_selftext":  empty_sel,
        "top_keywords":    [{"keyword": k, "count": v}
                            for k, v in kw_counter.most_common(10)],
    }


# ── Smoke test (no keyword filter) ───────────────────────────────────────────

def run_smoke_test(upload_drive: bool = False) -> SmokeResult:
    """
    Run a small Reddit parse with NO keyword filter.
    Goal: verify the client actually fetches posts and comments.
    0 posts / 0 comments → FAIL.
    """
    _check_reddit_env()

    ts      = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("exports", "smoke_test", ts)
    run_id  = f"smoke_{ts}"
    result  = SmokeResult(test_type="smoke", export_dir=out_dir)

    try:
        debug = {}
        posts_raw, comments_raw = _run_parse(
            subreddits=SMOKE_SUBREDDITS,
            keywords=SMOKE_KEYWORDS,     # [] → all posts pass
            period=SMOKE_PERIOD,
            sort=SMOKE_SORT,
            limit=SMOKE_LIMIT,
            max_comments=SMOKE_COMMENTS,
            min_score=SMOKE_MIN_SCORE,
            min_comments=SMOKE_MIN_COMMENTS,
            debug=debug,
        )

        # Store debug counters
        result.raw_posts_fetched = debug.get("raw_posts_fetched", 0)
        result.after_filter      = debug.get("after_filter", 0)
        result.final_posts       = debug.get("final_posts", 0)
        result.comments_fetched  = debug.get("comments_fetched", 0)

        # Quality metrics + deduplication
        m = _quality_metrics(posts_raw, comments_raw)
        result.posts_count           = m["posts_count"]
        result.comments_count        = m["comments_count"]
        result.duplicate_posts_removed = m["dup_removed"]
        result.bot_comments_count    = m["bot_comments"]
        result.empty_title_count     = m["empty_title"]
        result.empty_permalink_count = m["empty_permalink"]
        result.empty_selftext_count  = m["empty_selftext"]
        result.top_keywords          = m["top_keywords"]

        posts    = m["posts"]
        comments = m["comments"]

        # ── Determine status ──────────────────────────────────────────────────
        if result.posts_count == 0:
            result.status          = QA_FAIL
            result.warning_message = (
                f"FAIL: 0 posts fetched "
                f"(raw_posts_fetched={result.raw_posts_fetched}, "
                f"after_filter={result.after_filter}). "
                f"Check Reddit connectivity with --reddit-check."
            )
        elif result.comments_count == 0:
            result.status          = QA_FAIL
            result.warning_message = (
                f"FAIL: posts={result.posts_count} but 0 comments fetched "
                f"(comments_fetched={result.comments_fetched})."
            )
        elif result.posts_count < 20 or result.comments_count < 100:
            result.status          = QA_WARNING
            result.warning_message = (
                f"Small dataset: {result.posts_count} posts / "
                f"{result.comments_count} comments "
                f"(expected >=20 / >=100 for a full run)"
            )
        else:
            result.status = QA_PASS

        # ── Exports (always create, even when 0 posts) ────────────────────────
        exports = _build_exports(
            posts, comments, run_id=run_id, out_dir=out_dir,
            subreddits=SMOKE_SUBREDDITS, keywords=SMOKE_KEYWORDS,
            period=SMOKE_PERIOD, sort=SMOKE_SORT,
            limit=SMOKE_LIMIT, max_comments=SMOKE_COMMENTS,
            ts=ts,
        )
        result.xlsx_path         = exports["xlsx_path"]
        result.json_path         = exports["json_path"]
        result.handoff_json_path = exports["handoff_path"]

        if upload_drive:
            _smoke_drive_upload(result, exports["xlsx_path"])

        result.success = True

    except Exception as e:
        result.success = False
        result.status  = QA_FAIL
        result.error   = str(e)

    return result


# ── Keyword test (with keyword filter) ────────────────────────────────────────

def run_keyword_test() -> SmokeResult:
    """
    Run a wider parse with keyword filter to test keyword matching.
    Uses limit=50 per subreddit to get enough keyword matches.
    0 raw_posts_fetched → FAIL (network problem).
    0 after_filter → WARNING (no keyword matches found, network OK).
    """
    _check_reddit_env()

    ts      = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("exports", "keyword_test", ts)
    run_id  = f"keyword_{ts}"
    result  = SmokeResult(test_type="keyword", export_dir=out_dir)

    try:
        debug = {}
        posts_raw, comments_raw = _run_parse(
            subreddits=KW_SUBREDDITS,
            keywords=KW_KEYWORDS,
            period=KW_PERIOD,
            sort=KW_SORT,
            limit=KW_LIMIT,
            max_comments=KW_COMMENTS,
            min_score=KW_MIN_SCORE,
            min_comments=KW_MIN_COMMENTS,
            debug=debug,
        )

        result.raw_posts_fetched = debug.get("raw_posts_fetched", 0)
        result.after_filter      = debug.get("after_filter", 0)
        result.final_posts       = debug.get("final_posts", 0)
        result.comments_fetched  = debug.get("comments_fetched", 0)

        m = _quality_metrics(posts_raw, comments_raw)
        result.posts_count           = m["posts_count"]
        result.comments_count        = m["comments_count"]
        result.duplicate_posts_removed = m["dup_removed"]
        result.bot_comments_count    = m["bot_comments"]
        result.empty_title_count     = m["empty_title"]
        result.empty_permalink_count = m["empty_permalink"]
        result.empty_selftext_count  = m["empty_selftext"]
        result.top_keywords          = m["top_keywords"]

        posts    = m["posts"]
        comments = m["comments"]

        # ── Determine status ──────────────────────────────────────────────────
        if result.raw_posts_fetched == 0:
            result.status          = QA_FAIL
            result.warning_message = (
                f"FAIL: 0 raw posts fetched from Reddit. "
                f"Check connectivity with --reddit-check."
            )
        elif result.posts_count == 0:
            # Network OK but no keyword matches
            result.status          = QA_WARNING
            result.warning_message = (
                f"WARNING: fetched {result.raw_posts_fetched} raw posts "
                f"but 0 matched keywords {KW_KEYWORDS}. "
                f"This is unusual — try --parser-smoke-test to confirm network works."
            )
        elif result.posts_count < 5:
            result.status          = QA_WARNING
            result.warning_message = (
                f"Small keyword match: {result.posts_count} posts "
                f"(from {result.raw_posts_fetched} raw). "
                f"Keywords: {', '.join(KW_KEYWORDS)}"
            )
        else:
            result.status = QA_PASS

        # ── Exports ───────────────────────────────────────────────────────────
        exports = _build_exports(
            posts, comments, run_id=run_id, out_dir=out_dir,
            subreddits=KW_SUBREDDITS, keywords=KW_KEYWORDS,
            period=KW_PERIOD, sort=KW_SORT,
            limit=KW_LIMIT, max_comments=KW_COMMENTS,
            ts=ts,
        )
        result.xlsx_path         = exports["xlsx_path"]
        result.json_path         = exports["json_path"]
        result.handoff_json_path = exports["handoff_path"]

        result.success = True

    except Exception as e:
        result.success = False
        result.status  = QA_FAIL
        result.error   = str(e)

    return result


# ── Drive upload helper ────────────────────────────────────────────────────────

def _smoke_drive_upload(result: SmokeResult, xlsx_path: str) -> None:
    try:
        from drive_uploader import DRIVE_ENABLED, build_run_folder, upload_file
        if not DRIVE_ENABLED:
            result.drive_upload_status = "skipped (Drive not configured)"
            return
        folder_id = build_run_folder(0, "smoke_test", "smoke_test")
        info = upload_file(xlsx_path, folder_id)
        result.drive_xlsx_id     = info["file_id"]
        result.drive_xlsx_link   = info["web_view_link"]
        result.drive_upload_status = "ok"
    except Exception as e:
        result.drive_upload_status = f"error: {e}"


# ── QA file check ─────────────────────────────────────────────────────────────

def run_qa_file(xlsx_path: str) -> QAResult:
    """
    Inspect a finished export Excel file and return a QA summary.
    No network calls, no DB writes.
    """
    qa = QAResult(status=QA_FAIL, xlsx_path=xlsx_path)

    if not os.path.exists(xlsx_path):
        qa.errors.append(f"File not found: {xlsx_path}")
        return qa

    try:
        import pandas as pd
        xl = pd.ExcelFile(xlsx_path)
    except Exception as e:
        qa.errors.append(f"Cannot open Excel file: {e}")
        return qa

    qa.sheets_found   = xl.sheet_names
    qa.missing_sheets = sorted(REQUIRED_SHEETS - set(xl.sheet_names))

    if qa.missing_sheets:
        qa.errors.append(f"Missing required sheets: {qa.missing_sheets}")

    # ── Posts sheet ──────────────────────────────────────────────────────────
    posts_df = None
    if "Posts" in xl.sheet_names:
        try:
            posts_df = xl.parse("Posts")
            qa.total_posts = len(posts_df)

            if "title" in posts_df.columns:
                qa.empty_titles = int(
                    posts_df["title"].isna().sum() +
                    (posts_df["title"].astype(str).str.strip() == "").sum()
                )
            if "permalink" in posts_df.columns:
                qa.empty_permalinks = int(
                    posts_df["permalink"].isna().sum() +
                    (posts_df["permalink"].astype(str).str.strip() == "").sum()
                )
            if "post_id" in posts_df.columns:
                qa.duplicated_post_ids = int(posts_df["post_id"].duplicated().sum())
            if "trend_score" in posts_df.columns:
                qa.trend_score_zero_count = int(
                    (pd.to_numeric(posts_df["trend_score"],
                                   errors="coerce").fillna(0) == 0).sum()
                )
            if "selftext" in posts_df.columns:
                qa.empty_selftext_count = int(
                    posts_df["selftext"].isna().sum() +
                    (posts_df["selftext"].astype(str).str.strip() == "").sum()
                )
            if "pain_signal" in posts_df.columns:
                qa.pain_signal_distribution = dict(
                    posts_df["pain_signal"].value_counts().to_dict()
                )
            if "language_detected" in posts_df.columns:
                qa.language_distribution = dict(
                    posts_df["language_detected"].value_counts().to_dict()
                )
        except Exception as e:
            qa.errors.append(f"Error reading Posts sheet: {e}")

    # ── Comments sheet ───────────────────────────────────────────────────────
    if "Comments" in xl.sheet_names:
        try:
            comments_df = xl.parse("Comments")
            qa.total_comments = len(comments_df)
            if "is_bot_comment" in comments_df.columns:
                qa.bot_comments_count = int(
                    comments_df["is_bot_comment"].astype(str)
                    .str.lower()
                    .isin(["true", "1", "yes"])
                    .sum()
                )
        except Exception as e:
            qa.errors.append(f"Error reading Comments sheet: {e}")

    # ── Top Posts sheet ───────────────────────────────────────────────────────
    for sheet_name in xl.sheet_names:
        if "top" in sheet_name.lower() and "post" in sheet_name.lower():
            try:
                tp_df = xl.parse(sheet_name)
                qa.top_posts_count = len(tp_df)
            except Exception:
                pass
            break

    # ── Determine status ──────────────────────────────────────────────────────
    fail_reasons = []
    if qa.missing_sheets:
        fail_reasons.append(f"Missing sheets: {qa.missing_sheets}")
    if qa.total_posts == 0:
        fail_reasons.append("total_posts = 0")
    if qa.total_comments == 0:
        fail_reasons.append("total_comments = 0")
    if qa.empty_titles > 0:
        fail_reasons.append(f"empty_titles = {qa.empty_titles}")
    if qa.empty_permalinks > 0:
        fail_reasons.append(f"empty_permalinks = {qa.empty_permalinks}")
    if qa.bot_comments_count > 0:
        fail_reasons.append(f"bot_comments = {qa.bot_comments_count}")
    if qa.errors:
        fail_reasons.append("parser errors present")

    warn_reasons = []
    if qa.total_posts > 0:
        if qa.total_posts < 20:
            warn_reasons.append(f"total_posts < 20 ({qa.total_posts})")
        if qa.total_comments < 100:
            warn_reasons.append(f"total_comments < 100 ({qa.total_comments})")
        if posts_df is not None:
            selftext_pct = qa.empty_selftext_count / max(qa.total_posts, 1)
            if selftext_pct > 0.3:
                warn_reasons.append(
                    f"empty_selftext > 30% ({qa.empty_selftext_count}/{qa.total_posts})"
                )
            tscore_pct = qa.trend_score_zero_count / max(qa.total_posts, 1)
            if tscore_pct > 0.5:
                warn_reasons.append(
                    f"trend_score_zero > 50% ({qa.trend_score_zero_count}/{qa.total_posts})"
                )

    if fail_reasons:
        qa.status = QA_FAIL
        qa.errors.extend(fail_reasons)
    elif warn_reasons:
        qa.status = QA_WARNING
        qa.warnings.extend(warn_reasons)
    else:
        qa.status = QA_PASS

    return qa


# ── CLI printers ──────────────────────────────────────────────────────────────

def print_smoke_result(result: SmokeResult) -> None:
    W = 60
    label = "Parser Smoke Test" if result.test_type == "smoke" else "Parser Keyword Test"
    print()
    print("=" * W)
    print(f"  {label}")
    print("=" * W)

    if not result.success and result.error:
        print(f"  STATUS  : {result.status}")
        print(f"  Error   : {result.error}")
        if result.posts_count == 0:
            print("=" * W)
            return
        print()   # continue to show partial results if we have them

    print(f"  STATUS           : {result.status}")
    print(f"  posts_count      : {result.posts_count}")
    print(f"  comments_count   : {result.comments_count}")
    if result.warning_message:
        print(f"  note             : {result.warning_message}")
    print()
    print(f"  Debug counters:")
    print(f"    raw_posts_fetched   : {result.raw_posts_fetched}")
    print(f"    after_filter        : {result.after_filter}")
    print(f"    final_posts         : {result.final_posts}")
    print(f"    comments_fetched    : {result.comments_fetched}")
    print()
    print(f"  Data quality:")
    print(f"    bot_comments        : {result.bot_comments_count}")
    print(f"    empty_title         : {result.empty_title_count}")
    print(f"    empty_permalink     : {result.empty_permalink_count}")
    print(f"    empty_selftext      : {result.empty_selftext_count}")
    print(f"    duplicate_posts_rm  : {result.duplicate_posts_removed}")

    if result.top_keywords:
        print()
        kw_str = ", ".join(f"{k['keyword']} ({k['count']})"
                           for k in result.top_keywords[:8])
        print(f"  top_keywords     : {kw_str}")

    print()
    print(f"  Export dir       : {result.export_dir}")
    if result.xlsx_path:
        print(f"  xlsx_path        : {result.xlsx_path}")
    if result.json_path:
        print(f"  json_path        : {result.json_path}")
    if result.handoff_json_path:
        print(f"  handoff_json     : {result.handoff_json_path}")

    if result.drive_upload_status != "skipped":
        print()
        print(f"  Drive upload     : {result.drive_upload_status}")
        if result.drive_xlsx_id:
            print(f"  drive_file_id    : {result.drive_xlsx_id}")
        if result.drive_xlsx_link:
            print(f"  drive_view_link  : {result.drive_xlsx_link}")

    print("=" * W)
    print()


def print_qa_result(qa: QAResult) -> None:
    WIDTH = 60
    status_icons = {QA_PASS: "[PASS]", QA_WARNING: "[WARNING]", QA_FAIL: "[FAIL]"}

    print()
    print("=" * WIDTH)
    print("  Parser QA Report")
    print("=" * WIDTH)
    print(f"  File             : {qa.xlsx_path}")
    print(f"  STATUS           : {status_icons.get(qa.status, qa.status)}")
    print()
    print(f"  Sheets found     : {', '.join(qa.sheets_found) or '(none)'}")
    if qa.missing_sheets:
        print(f"  Missing sheets   : {', '.join(qa.missing_sheets)}")
    print()
    print(f"  total_posts      : {qa.total_posts}")
    print(f"  total_comments   : {qa.total_comments}")
    if qa.top_posts_count:
        print(f"  top_posts_count  : {qa.top_posts_count}")
    print()
    print(f"  Data quality:")
    print(f"    empty_titles          : {qa.empty_titles}")
    print(f"    empty_permalinks      : {qa.empty_permalinks}")
    print(f"    bot_comments_count    : {qa.bot_comments_count}")
    print(f"    duplicated_post_ids   : {qa.duplicated_post_ids}")
    print(f"    trend_score_zero      : {qa.trend_score_zero_count}")
    print(f"    empty_selftext        : {qa.empty_selftext_count}")

    if qa.pain_signal_distribution:
        print()
        print(f"  Pain signals:")
        for sig, cnt in sorted(qa.pain_signal_distribution.items(),
                                key=lambda x: -x[1]):
            print(f"    {sig:<25} : {cnt}")

    if qa.language_distribution:
        print()
        print(f"  Languages:")
        for lang, cnt in sorted(qa.language_distribution.items(),
                                 key=lambda x: -x[1]):
            print(f"    {lang:<25} : {cnt}")

    if qa.warnings:
        print()
        print("  Warnings:")
        for w in qa.warnings:
            print(f"    - {w}")

    if qa.errors:
        print()
        print("  Errors:")
        for e in qa.errors:
            print(f"    - {e}")

    print("=" * WIDTH)
    print()
