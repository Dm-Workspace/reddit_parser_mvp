"""
Monitor Runner — executes a single monitor run end-to-end:
  1. Load monitor + project from DB
  2. Resolve subreddits and keywords (preset or custom)
  3. Create/update run record (metadata only — no raw text in DB)
  4. Scrape Reddit via Playwright
  5. Export files (xlsx / json / handoff)
  6. Upload to Google Drive (non-fatal if fails → completed_with_warning)
  7. Clean up local files if upload succeeded and CLEANUP_LOCAL_FILES=true
  8. Update run record + monitor last_run_at / next_run_at

PostgreSQL policy:
  - Only compact metadata is stored in DB
  - Full post/comment data lives exclusively in exported files on Google Drive
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from loguru import logger

from config import (
    KEYWORD_PRESETS, SUBREDDIT_PRESETS, RUN_MODES, EXPORTS_DIR,
    SMALL_DATASET_MIN_POSTS, SMALL_DATASET_MIN_COMMENTS,
)
from reddit_client import create_reddit_client, close_reddit_client
from reddit_parser import parse_subreddits
from utils.deduplication import deduplicate_posts, deduplicate_comments
from utils.date_utils import now_utc_str, now_file_str
from storage import database as db
from storage.models import Run, Export, Monitor, Project
from storage.models import RUN_QUEUED, RUN_RUNNING, RUN_COMPLETED, RUN_COMPLETED_WARNING, RUN_FAILED
from exporters.handoff_exporter import get_top_keywords_for_db

MAX_POSTS_TOTAL    = int(os.environ.get("MAX_POSTS_TOTAL", "500"))
MAX_COMMENTS_TOTAL = int(os.environ.get("MAX_COMMENTS_TOTAL", "5000"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _load_project(monitor: Monitor) -> Project:
    project = db.get_project(monitor.project_id)
    if not project:
        project = Project(
            id=monitor.project_id, owner_telegram_id=monitor.owner_telegram_id,
            name=monitor.project_id, description="", niche="",
            output_language="en", enabled=True, archived=False,
        )
    return project


def _resolve_subreddits(monitor: Monitor) -> List[str]:
    """Resolve subreddits from preset or custom list."""
    if monitor.subreddit_preset_id:
        preset = db.get_subreddit_preset(monitor.subreddit_preset_id)
        if preset and preset.subreddits:
            return json.loads(preset.subreddits)
        cfg = SUBREDDIT_PRESETS.get(monitor.subreddit_preset_id)
        if cfg:
            return cfg

    if monitor.custom_subreddits and monitor.custom_subreddits != "[]":
        return json.loads(monitor.custom_subreddits)

    logger.warning(f"Monitor {monitor.id}: no subreddits configured")
    return []


def _resolve_keywords(monitor: Monitor) -> List[str]:
    """Resolve keywords from preset or custom list."""
    if monitor.keyword_preset_id:
        preset = db.get_keyword_preset(monitor.keyword_preset_id)
        if preset and preset.keywords:
            return json.loads(preset.keywords)
        cfg = KEYWORD_PRESETS.get(monitor.keyword_preset_id)
        if cfg:
            return cfg

    if monitor.custom_keywords and monitor.custom_keywords != "[]":
        return json.loads(monitor.custom_keywords)

    return []  # no keyword filter = collect all posts


def _language_mode(monitor: Monitor) -> str:
    if monitor.keyword_preset_id:
        if monitor.keyword_preset_id.endswith("_ru"):
            return "ru"
        if monitor.keyword_preset_id.endswith("_uk"):
            return "uk"
        if monitor.keyword_preset_id.endswith("_en"):
            return "en"
    return "mixed"


def _compute_next_run_at(monitor: Monitor) -> Optional[str]:
    if monitor.schedule_mode != "scheduled":
        return None
    try:
        from bot.schedule_utils import compute_next_run_at
        return compute_next_run_at(
            monitor.frequency, monitor.schedule_cron, monitor.timezone,
            from_dt=datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.warning(f"compute_next_run_at failed for {monitor.id}: {e}")
        return None


def run_monitor(monitor_id: str, existing_run_id: str = None) -> Optional[Run]:
    """
    Execute a full monitor run. Returns the final Run record.
    Never raises — all exceptions are caught and stored in run.error_message.
    """
    db.init_db()
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        logger.error(f"Monitor '{monitor_id}' not found")
        return None
    if not monitor.enabled or monitor.archived:
        logger.warning(f"Monitor '{monitor_id}' is disabled/archived, skipping")
        return None
    if monitor.schedule_mode == "disabled":
        logger.warning(f"Monitor '{monitor_id}' schedule_mode=disabled, skipping")
        return None

    active = db.get_active_run_for_monitor(monitor_id)
    if active and active.id != existing_run_id:
        logger.warning(f"Monitor '{monitor_id}' already running ({active.id})")
        return active

    project    = _load_project(monitor)
    subreddits = _resolve_subreddits(monitor)
    keywords   = _resolve_keywords(monitor)
    lang_mode  = _language_mode(monitor)

    if not subreddits:
        logger.error(f"Monitor '{monitor_id}' has no subreddits — aborting")
        return None

    # ── Create or reuse run record ─────────────────────────────────────────────
    if existing_run_id:
        run = db.get_run(existing_run_id)
        if not run:
            return None
        run.status     = RUN_RUNNING
        run.started_at = _utc_now()
    else:
        run = Run(
            id=str(uuid.uuid4())[:12],
            monitor_id=monitor_id,
            project_id=monitor.project_id,
            owner_telegram_id=monitor.owner_telegram_id,
            status=RUN_RUNNING,
            started_at=_utc_now(),
        )
        db.create_run(run)

    logger.info(
        f"▶ Run {run.id} — monitor: {monitor.name} | "
        f"{len(subreddits)} subs | {len(keywords)} kw"
    )

    try:
        mode_cfg         = RUN_MODES.get(monitor.run_mode, {})
        sort             = mode_cfg.get("sort", "hot")
        period           = mode_cfg.get("period", "last_7d")
        limit            = mode_cfg.get("limit", 50)
        max_comments     = mode_cfg.get("comments", 20)
        min_score        = mode_cfg.get("min_score", 3)
        min_comments_cnt = mode_cfg.get("min_comments", 5)

        run_settings = {
            "run_date":              now_utc_str(),
            "run_id":                run.id,
            "monitor_id":            monitor_id,
            "monitor_name":          monitor.name,
            "project_id":            monitor.project_id,
            "owner_telegram_id":     str(monitor.owner_telegram_id),
            "subreddits":            ", ".join(subreddits),
            "subreddit_preset":      monitor.subreddit_preset_id or "custom",
            "keywords":              ", ".join(keywords) if keywords else "all",
            "keyword_preset":        monitor.keyword_preset_id or "custom",
            "period":                period,
            "sort":                  sort,
            "run_mode":              monitor.run_mode,
            "limit_per_subreddit":   limit,
            "max_comments_per_post": max_comments,
            "min_score":             min_score,
            "min_comments":          min_comments_cnt,
            "language_mode":         lang_mode,
            "filter_bots":           True,
            "fetch_selftext":        True,
            "export_format":         json.loads(monitor.export_formats),
        }

        # ── Scrape ────────────────────────────────────────────────────────────
        reddit = create_reddit_client()
        try:
            posts, comments = parse_subreddits(
                reddit=reddit, subreddits=subreddits, keywords=keywords,
                period=period, sort=sort, limit=limit, max_comments=max_comments,
                min_score=min_score, min_comments=min_comments_cnt,
                language_mode=lang_mode,
            )
        finally:
            close_reddit_client(reddit)

        posts    = deduplicate_posts(posts)[:MAX_POSTS_TOTAL]
        comments = deduplicate_comments(comments)[:MAX_COMMENTS_TOTAL]
        logger.info(f"Collected: {len(posts)} posts, {len(comments)} comments")

        # ── Export files ──────────────────────────────────────────────────────
        owner_dir = str(monitor.owner_telegram_id) if monitor.owner_telegram_id else "system"
        run_dir   = os.path.join(
            EXPORTS_DIR, owner_dir, monitor.project_id, monitor_id, run.id
        )
        os.makedirs(run_dir, exist_ok=True)

        export_formats = json.loads(monitor.export_formats)
        export_records: List[Export] = []

        def _mk_export(fmt: str, path: str) -> Export:
            size = None
            try:
                size = os.path.getsize(path) if os.path.exists(path) else None
            except Exception:
                pass
            return Export(
                id=str(uuid.uuid4())[:12],
                run_id=run.id,
                format=fmt,
                file_path=path,
                file_name=os.path.basename(path),
                file_size=size,
                owner_telegram_id=monitor.owner_telegram_id,
                project_id=monitor.project_id,
                monitor_id=monitor_id,
            )

        if "xlsx" in export_formats:
            from exporters.excel_exporter import export_excel
            path = os.path.join(run_dir, f"{run.id}.xlsx")
            export_excel(posts, comments, run_settings, path, all_subreddits=subreddits)
            exp = _mk_export("xlsx", path)
            db.create_export(exp)
            export_records.append(exp)

        if "csv" in export_formats:
            from exporters.csv_exporter import export_csv
            prefix   = os.path.join(run_dir, f"{run.id}")
            p_path, c_path = export_csv(posts, comments, prefix)
            for path, fmt in [(p_path, "csv_posts"), (c_path, "csv_comments")]:
                exp = _mk_export(fmt, path)
                db.create_export(exp)
                export_records.append(exp)

        if "json" in export_formats:
            from exporters.json_exporter import export_json
            path = os.path.join(run_dir, f"{run.id}.json")
            export_json(posts, comments, run_settings, path)
            exp = _mk_export("json", path)
            db.create_export(exp)
            export_records.append(exp)

        # Handoff JSON — always
        from exporters.handoff_exporter import export_handoff
        handoff_path = export_handoff(
            posts=posts, comments=comments,
            run=run, monitor=monitor, project=project,
            run_settings=run_settings, output_dir=run_dir,
        )
        exp_h = _mk_export("handoff_json", handoff_path)
        db.create_export(exp_h)
        export_records.append(exp_h)

        # ── Drive upload (non-fatal) ───────────────────────────────────────────
        drive_warning = False
        try:
            from drive_uploader import DRIVE_ENABLED, upload_run_exports
            if DRIVE_ENABLED:
                drive_results, drive_had_errors = upload_run_exports(
                    export_records, monitor.owner_telegram_id,
                    monitor.project_id, monitor_id
                )
                if drive_had_errors:
                    drive_warning = True
                    logger.warning(f"Run {run.id}: some Drive uploads failed")
                for exp in export_records:
                    info = drive_results.get(exp.id)
                    if info:
                        db.update_export_drive(
                            exp.id, info["file_id"],
                            info["web_view_link"], info["download_link"],
                            info.get("file_size"),
                        )
                        exp.drive_file_id       = info["file_id"]
                        exp.drive_web_view_link = info["web_view_link"]
                        exp.drive_download_link = info["download_link"]
        except Exception as e:
            logger.error(f"Drive upload block failed: {e}")
            drive_warning = True

        # ── Finalise run ──────────────────────────────────────────────────────
        small = (
            len(posts) < SMALL_DATASET_MIN_POSTS or
            len(comments) < SMALL_DATASET_MIN_COMMENTS
        )
        if run.status == RUN_RUNNING:  # only update if not already failed
            if small or drive_warning:
                run.status = RUN_COMPLETED_WARNING
            else:
                run.status = RUN_COMPLETED

        run.finished_at       = _utc_now()
        run.total_posts       = len(posts)
        run.total_comments    = len(comments)
        run.quality_status    = "small_dataset" if small else "ok"

        warnings = []
        if small:
            warnings.append(
                f"Small dataset: {len(posts)} posts / {len(comments)} comments"
            )
        if drive_warning:
            warnings.append("Some Drive uploads failed — files kept locally")
        run.warning_message   = "; ".join(warnings) if warnings else None

        run.export_path       = run_dir
        run.handoff_json_path = handoff_path
        run.top_keywords_json = get_top_keywords_for_db(posts, n=10)
        db.update_run(run)

        # Update monitor tracking fields
        next_run_at = _compute_next_run_at(monitor)
        db.update_monitor_after_run(monitor_id, _utc_now(), next_run_at)

        logger.success(
            f"✓ Run {run.id} {run.status} — "
            f"{len(posts)}p / {len(comments)}c | {run_dir}"
        )
        return run

    except Exception as e:
        logger.exception(f"Run {run.id} failed: {e}")
        run.status        = RUN_FAILED
        run.finished_at   = _utc_now()
        run.error_message = str(e)[:500]
        db.update_run(run)
        return run
