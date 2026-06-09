"""
Parser QA / Smoke-test module.

Two entry points:
  run_smoke_test(upload_drive=False) -> SmokeResult
  run_qa_file(xlsx_path) -> QAResult

Both are called from main_runner.py CLI flags.
No Telegram, no Railway, no full DB needed.
SQLite fallback works out of the box.

Reddit ENV check:
  If REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are missing, raises RuntimeError
  before touching the network.
"""
import json
import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


# ── Constants ──────────────────────────────────────────────────────────────────

SMOKE_SUBREDDITS = ["Supplements", "Biohackers"]
SMOKE_KEYWORDS   = ["magnesium", "sleep", "fatigue"]
SMOKE_PERIOD     = "last_7d"
SMOKE_SORT       = "hot"
SMOKE_LIMIT      = 10
SMOKE_COMMENTS   = 5
SMOKE_MIN_SCORE  = 0
SMOKE_MIN_COMMENTS = 0

REQUIRED_SHEETS = {"Posts", "Comments", "Summary"}
QA_PASS    = "PASS"
QA_WARNING = "WARNING"
QA_FAIL    = "FAIL"


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class SmokeResult:
    success: bool
    error: Optional[str]            = None
    posts_count: int                = 0
    comments_count: int             = 0
    bot_comments_count: int         = 0
    empty_title_count: int          = 0
    empty_permalink_count: int      = 0
    empty_selftext_count: int       = 0
    duplicate_posts_removed: int    = 0
    top_keywords: List[dict]        = field(default_factory=list)
    quality_status: str             = "ok"
    warning_message: Optional[str] = None
    export_dir: str                 = ""
    xlsx_path: Optional[str]        = None
    json_path: Optional[str]        = None
    handoff_json_path: Optional[str] = None
    # Drive (only when --upload-drive)
    drive_xlsx_id: Optional[str]    = None
    drive_xlsx_link: Optional[str]  = None
    drive_upload_status: str        = "skipped"


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
    missing = []
    if not os.environ.get("REDDIT_CLIENT_ID"):
        missing.append("REDDIT_CLIENT_ID")
    if not os.environ.get("REDDIT_CLIENT_SECRET"):
        missing.append("REDDIT_CLIENT_SECRET")
    if missing:
        raise RuntimeError(
            f"Reddit API ENV vars not set: {', '.join(missing)}\n"
            f"Create a script app at https://www.reddit.com/prefs/apps\n"
            f"Then set these variables in your .env or Railway ENV."
        )


# ── Smoke test ────────────────────────────────────────────────────────────────

def run_smoke_test(upload_drive: bool = False) -> SmokeResult:
    """
    Run a small Reddit parse against known safe subreddits.
    Never writes raw post/comment data to DB.
    Saves export files to exports/smoke_test/{timestamp}/.
    """
    _check_reddit_env()

    ts      = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("exports", "smoke_test", ts)
    os.makedirs(out_dir, exist_ok=True)

    result = SmokeResult(success=False, export_dir=out_dir)

    try:
        from reddit_client import create_reddit_client, close_reddit_client
        from reddit_parser import parse_subreddits
        from utils.deduplication import deduplicate_posts, deduplicate_comments
        from config import SMALL_DATASET_MIN_POSTS, SMALL_DATASET_MIN_COMMENTS

        reddit = create_reddit_client()
        try:
            posts_raw, comments_raw = parse_subreddits(
                reddit=reddit,
                subreddits=SMOKE_SUBREDDITS,
                keywords=SMOKE_KEYWORDS,
                period=SMOKE_PERIOD,
                sort=SMOKE_SORT,
                limit=SMOKE_LIMIT,
                max_comments=SMOKE_COMMENTS,
                min_score=SMOKE_MIN_SCORE,
                min_comments=SMOKE_MIN_COMMENTS,
                language_mode="mixed",
            )
        finally:
            close_reddit_client(reddit)

        # Deduplication stats
        pre_dedup = len(posts_raw)
        posts    = deduplicate_posts(posts_raw)
        comments = deduplicate_comments(comments_raw)
        result.duplicate_posts_removed = pre_dedup - len(posts)

        result.posts_count    = len(posts)
        result.comments_count = len(comments)

        # QA metrics on raw data
        result.bot_comments_count    = sum(1 for c in comments if getattr(c, "is_bot_comment", False))
        result.empty_title_count     = sum(1 for p in posts if not (p.title or "").strip())
        result.empty_permalink_count = sum(1 for p in posts if not (p.permalink or "").strip())
        result.empty_selftext_count  = sum(1 for p in posts if not (p.selftext or "").strip())

        # Top keywords
        kw_counter: Counter = Counter()
        for p in posts:
            for kw in (p.matched_keywords or "").split(", "):
                kw = kw.strip()
                if kw:
                    kw_counter[kw] += 1
        result.top_keywords = [{"keyword": k, "count": v} for k, v in kw_counter.most_common(10)]

        # Quality status
        small = (
            result.posts_count    < SMALL_DATASET_MIN_POSTS or
            result.comments_count < SMALL_DATASET_MIN_COMMENTS
        )
        result.quality_status = "small_dataset" if small else "ok"
        if small:
            result.warning_message = (
                f"Small dataset: {result.posts_count} posts / {result.comments_count} comments "
                f"(min {SMALL_DATASET_MIN_POSTS} / {SMALL_DATASET_MIN_COMMENTS})"
            )

        # ── Exports ───────────────────────────────────────────────────────────
        run_id = f"smoke_{ts}"
        run_settings = {
            "run_date":    ts,
            "run_id":      run_id,
            "monitor_id":  "smoke_test",
            "monitor_name": "Smoke Test",
            "project_id":  "smoke_test",
            "owner_telegram_id": "0",
            "subreddits":  ", ".join(SMOKE_SUBREDDITS),
            "subreddit_preset": "custom",
            "keywords":    ", ".join(SMOKE_KEYWORDS),
            "keyword_preset": "custom",
            "period":      SMOKE_PERIOD,
            "sort":        SMOKE_SORT,
            "run_mode":    "hot_last_7d",
            "limit_per_subreddit":   SMOKE_LIMIT,
            "max_comments_per_post": SMOKE_COMMENTS,
            "min_score":   SMOKE_MIN_SCORE,
            "min_comments": SMOKE_MIN_COMMENTS,
            "language_mode": "mixed",
            "filter_bots": True,
            "fetch_selftext": True,
            "export_format": ["xlsx", "json"],
        }

        # XLSX
        from exporters.excel_exporter import export_excel
        xlsx_path = os.path.join(out_dir, f"{run_id}.xlsx")
        export_excel(posts, comments, run_settings, xlsx_path, all_subreddits=SMOKE_SUBREDDITS)
        result.xlsx_path = xlsx_path

        # JSON
        from exporters.json_exporter import export_json
        json_path = os.path.join(out_dir, f"{run_id}.json")
        export_json(posts, comments, run_settings, json_path)
        result.json_path = json_path

        # Handoff JSON (needs mock Run/Monitor/Project objects)
        from exporters.handoff_exporter import export_handoff
        from storage.models import Run, Monitor, Project, RUN_COMPLETED

        mock_run = Run(
            id=run_id, monitor_id="smoke_test", project_id="smoke_test",
            status=RUN_COMPLETED, started_at=ts,
            total_posts=result.posts_count, total_comments=result.comments_count,
            quality_status=result.quality_status, warning_message=result.warning_message,
        )
        mock_monitor = Monitor(
            id="smoke_test", project_id="smoke_test", name="Smoke Test",
            custom_subreddits=json.dumps(SMOKE_SUBREDDITS),
            custom_keywords=json.dumps(SMOKE_KEYWORDS),
            run_mode="hot_last_7d",
        )
        mock_project = Project(
            id="smoke_test", name="Smoke Test",
            description="Parser smoke test run",
        )
        handoff_path = export_handoff(
            posts=posts, comments=comments,
            run=mock_run, monitor=mock_monitor, project=mock_project,
            run_settings=run_settings, output_dir=out_dir,
        )
        result.handoff_json_path = handoff_path

        # ── Drive upload (optional) ───────────────────────────────────────────
        if upload_drive:
            _smoke_drive_upload(result, xlsx_path)

        result.success = True

    except Exception as e:
        result.success = False
        result.error   = str(e)

    return result


def _smoke_drive_upload(result: SmokeResult, xlsx_path: str) -> None:
    try:
        from drive_uploader import DRIVE_ENABLED, build_run_folder, upload_file
        if not DRIVE_ENABLED:
            result.drive_upload_status = "skipped (Drive not configured)"
            return
        folder_id = build_run_folder(0, "smoke_test", "smoke_test")
        info      = upload_file(xlsx_path, folder_id)
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

    qa.sheets_found  = xl.sheet_names
    qa.missing_sheets = sorted(REQUIRED_SHEETS - set(xl.sheet_names))

    if qa.missing_sheets:
        qa.errors.append(f"Missing required sheets: {qa.missing_sheets}")
        # Still try to read what we have

    # ── Posts sheet ──────────────────────────────────────────────────────────
    posts_df = None
    if "Posts" in xl.sheet_names:
        try:
            posts_df = xl.parse("Posts")
            qa.total_posts = len(posts_df)

            # empty titles
            if "title" in posts_df.columns:
                qa.empty_titles = int(posts_df["title"].isna().sum() +
                                      (posts_df["title"].astype(str).str.strip() == "").sum())

            # empty permalinks
            if "permalink" in posts_df.columns:
                qa.empty_permalinks = int(posts_df["permalink"].isna().sum() +
                                          (posts_df["permalink"].astype(str).str.strip() == "").sum())

            # duplicate post IDs
            if "post_id" in posts_df.columns:
                qa.duplicated_post_ids = int(posts_df["post_id"].duplicated().sum())

            # trend_score zeros
            if "trend_score" in posts_df.columns:
                qa.trend_score_zero_count = int(
                    (pd.to_numeric(posts_df["trend_score"], errors="coerce").fillna(0) == 0).sum()
                )

            # empty selftext
            if "selftext" in posts_df.columns:
                qa.empty_selftext_count = int(
                    posts_df["selftext"].isna().sum() +
                    (posts_df["selftext"].astype(str).str.strip() == "").sum()
                )

            # pain_signal distribution
            if "pain_signal" in posts_df.columns:
                qa.pain_signal_distribution = dict(
                    posts_df["pain_signal"].value_counts().to_dict()
                )

            # language distribution
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

    # ── Top Posts sheet (may be called "Top Posts" or "TopPosts") ─────────────
    for sheet_name in xl.sheet_names:
        if "top" in sheet_name.lower() and "post" in sheet_name.lower():
            try:
                tp_df = xl.parse(sheet_name)
                qa.top_posts_count = len(tp_df)
            except Exception:
                pass
            break

    # ── Determine status ──────────────────────────────────────────────────────
    # FAIL conditions
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

    # WARNING conditions (only if not already FAIL)
    warn_reasons = []
    if qa.total_posts > 0:
        if qa.total_posts < 20:
            warn_reasons.append(f"total_posts < 20 ({qa.total_posts})")
        if qa.total_comments < 100:
            warn_reasons.append(f"total_comments < 100 ({qa.total_comments})")
        if posts_df is not None and qa.total_posts > 0:
            selftext_pct = qa.empty_selftext_count / qa.total_posts
            if selftext_pct > 0.3:
                warn_reasons.append(
                    f"empty_selftext > 30% ({qa.empty_selftext_count}/{qa.total_posts})"
                )
            tscore_pct = qa.trend_score_zero_count / qa.total_posts
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
    print()
    print("=" * 55)
    print("  Parser Smoke Test")
    print("=" * 55)

    if not result.success:
        print(f"  STATUS  : FAIL")
        print(f"  Error   : {result.error}")
        print("=" * 55)
        return

    ok_warn = "ok" if result.quality_status == "ok" else "WARNING"
    print(f"  STATUS           : {ok_warn}")
    print(f"  posts_count      : {result.posts_count}")
    print(f"  comments_count   : {result.comments_count}")
    if result.warning_message:
        print(f"  warning          : {result.warning_message}")
    print()
    print(f"  Data quality:")
    print(f"    bot_comments        : {result.bot_comments_count}")
    print(f"    empty_title         : {result.empty_title_count}")
    print(f"    empty_permalink     : {result.empty_permalink_count}")
    print(f"    empty_selftext      : {result.empty_selftext_count}")
    print(f"    duplicate_posts_rm  : {result.duplicate_posts_removed}")
    print()
    if result.top_keywords:
        kw_str = ", ".join(f"{k['keyword']} ({k['count']})" for k in result.top_keywords[:6])
        print(f"  top_keywords     : {kw_str}")
    print()
    print(f"  Export dir       : {result.export_dir}")
    print(f"  xlsx_path        : {result.xlsx_path}")
    print(f"  json_path        : {result.json_path}")
    print(f"  handoff_json     : {result.handoff_json_path}")

    if result.drive_upload_status != "skipped":
        print()
        print(f"  Drive upload     : {result.drive_upload_status}")
        if result.drive_xlsx_id:
            print(f"  drive_file_id    : {result.drive_xlsx_id}")
        if result.drive_xlsx_link:
            print(f"  drive_view_link  : {result.drive_xlsx_link}")

    print("=" * 55)
    print()


def print_qa_result(qa: QAResult) -> None:
    WIDTH = 55
    status_icons = {QA_PASS: "[PASS]", QA_WARNING: "[WARNING]", QA_FAIL: "[FAIL]"}

    print()
    print("=" * WIDTH)
    print("  Parser QA Report")
    print("=" * WIDTH)
    print(f"  File             : {qa.xlsx_path}")
    print(f"  STATUS           : {status_icons[qa.status]}")
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
        for sig, cnt in sorted(qa.pain_signal_distribution.items(), key=lambda x: -x[1]):
            print(f"    {sig:<22} : {cnt}")

    if qa.language_distribution:
        print()
        print(f"  Languages:")
        for lang, cnt in sorted(qa.language_distribution.items(), key=lambda x: -x[1]):
            print(f"    {lang:<22} : {cnt}")

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
