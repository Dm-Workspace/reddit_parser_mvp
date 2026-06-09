"""
Monitor Runner
Executes a single monitor run end-to-end:
  1. Load monitor + project from DB
  2. Create/update run record
  3. Parse Reddit via Playwright
  4. Export files (xlsx / json / handoff)
  5. Upload files to Google Drive (if configured)
  6. Clean up local files (optional)
  7. Update run record with final status
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List
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
from storage.models import (
    RUN_QUEUED, RUN_RUNNING, RUN_COMPLETED, RUN_COMPLETED_WARNING, RUN_FAILED
)
from exporters.handoff_exporter import get_top_keywords_for_db

# Drive upload is optional
CLEANUP_LOCAL = os.environ.get("CLEANUP_LOCAL_FILES", "false").lower() == "true"

# Limits per run (override via ENV)
MAX_POSTS_TOTAL    = int(os.environ.get("MAX_POSTS_TOTAL", "500"))
MAX_COMMENTS_TOTAL = int(os.environ.get("MAX_COMMENTS_TOTAL", "5000"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _load_project(monitor: Monitor) -> Project:
    project = db.get_project(monitor.project_id)
    if not project:
        logger.warning(f"Project '{monitor.project_id}' not found, using defaults")
        project = Project(
            id=monitor.project_id, name=monitor.project_id,
            description="", language="en", market="",
            default_output_language="en", enabled=True,
        )
    return project


def _language_mode(keyword_preset: str) -> str:
    EN_PRESETS = {"wellness_en", "crm_en", "ai_en"}
    RU_PRESETS = {"wellness_ru"}
    if keyword_preset in EN_PRESETS:
        return "en"
    elif keyword_preset in RU_PRESETS:
        return "ru"
    return "mixed"


def run_monitor(monitor_id: str, existing_run_id: str = None) -> Optional[Run]:
    """
    Execute a full monitor run. Returns the final Run record.

    Args:
        monitor_id:      ID of the monitor to run
        existing_run_id: If set, update this existing Run record (status was 'queued')
                         instead of creating a new one.
    """
    db.init_db()
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        logger.error(f"Monitor '{monitor_id}' not found. Run 'list-monitors' or sync first.")
        return None
    if not monitor.enabled:
        logger.warning(f"Monitor '{monitor_id}' is disabled, skipping")
        return None

    # Guard: don't double-run
    active = db.get_active_run_for_monitor(monitor_id)
    if active and active.id != existing_run_id:
        logger.warning(f"Monitor '{monitor_id}' already has an active run ({active.id}), skipping")
        return active

    project = _load_project(monitor)

    # Create or reuse run record
    if existing_run_id:
        run = db.get_run(existing_run_id)
        if not run:
            logger.error(f"Run {existing_run_id} not found in DB")
            return None
        run.status     = RUN_RUNNING
        run.started_at = _utc_now()
    else:
        run = Run(
            id=str(uuid.uuid4())[:12],
            monitor_id=monitor_id,
            project_id=monitor.project_id,
            status=RUN_RUNNING,
            started_at=_utc_now(),
        )
        db.create_run(run)

    logger.info(f"▶ Run {run.id} started — monitor: {monitor.name}")

    try:
        # ── Parse settings ────────────────────────────────────────────────────
        mode_cfg         = RUN_MODES.get(monitor.run_mode, {})
        sort             = mode_cfg.get("sort", "hot")
        period           = mode_cfg.get("period", "last_7d")
        limit            = mode_cfg.get("limit", 50)
        max_comments     = mode_cfg.get("comments", 20)
        min_score        = mode_cfg.get("min_score", 3)
        min_comments_cnt = mode_cfg.get("min_comments", 5)

        keywords   = KEYWORD_PRESETS.get(monitor.keyword_preset, [])
        subreddits = SUBREDDIT_PRESETS.get(monitor.subreddit_preset, [])
        lang_mode  = _language_mode(monitor.keyword_preset)

        run_settings = {
            "run_date":              now_utc_str(),
            "run_id":                run.id,
            "monitor_id":            monitor_id,
            "monitor_name":          monitor.name,
            "project_id":            monitor.project_id,
            "subreddits":            ", ".join(subreddits),
            "subreddit_preset":      monitor.subreddit_preset,
            "keywords":              ", ".join(keywords) if keywords else "all",
            "keyword_preset":        monitor.keyword_preset,
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
                reddit=reddit,
                subreddits=subreddits,
                keywords=keywords,
                period=period,
                sort=sort,
                limit=limit,
                max_comments=max_comments,
                min_score=min_score,
                min_comments=min_comments_cnt,
                language_mode=lang_mode,
            )
        finally:
            close_reddit_client(reddit)

        posts    = deduplicate_posts(posts)
        comments = deduplicate_comments(comments)

        # Apply total limits
        posts    = posts[:MAX_POSTS_TOTAL]
        comments = comments[:MAX_COMMENTS_TOTAL]
        logger.info(f"Collected: {len(posts)} posts, {len(comments)} comments")

        # ── Export dir ────────────────────────────────────────────────────────
        run_dir = os.path.join(EXPORTS_DIR, monitor.project_id, monitor_id, run.id)
        os.makedirs(run_dir, exist_ok=True)

        export_formats  = json.loads(monitor.export_formats)
        export_records: List[Export] = []
        ts = now_file_str()

        if "xlsx" in export_formats:
            from exporters.excel_exporter import export_excel
            xlsx_path = os.path.join(run_dir, f"report_{ts}.xlsx")
            export_excel(posts, comments, run_settings, xlsx_path,
                         all_subreddits=subreddits)
            exp = Export(id=str(uuid.uuid4())[:12], run_id=run.id,
                         format="xlsx", file_path=xlsx_path)
            db.create_export(exp)
            export_records.append(exp)

        if "csv" in export_formats:
            from exporters.csv_exporter import export_csv
            prefix = os.path.join(run_dir, f"report_{ts}")
            posts_path, comments_path = export_csv(posts, comments, prefix)
            for path, fmt in [(posts_path, "csv_posts"), (comments_path, "csv_comments")]:
                exp = Export(id=str(uuid.uuid4())[:12], run_id=run.id,
                             format=fmt, file_path=path)
                db.create_export(exp)
                export_records.append(exp)

        if "json" in export_formats:
            from exporters.json_exporter import export_json
            json_path = os.path.join(run_dir, f"report_{ts}.json")
            export_json(posts, comments, run_settings, json_path)
            exp = Export(id=str(uuid.uuid4())[:12], run_id=run.id,
                         format="json", file_path=json_path)
            db.create_export(exp)
            export_records.append(exp)

        # Handoff JSON — always
        from exporters.handoff_exporter import export_handoff
        handoff_path = export_handoff(
            posts=posts, comments=comments,
            run=run, monitor=monitor, project=project,
            run_settings=run_settings, output_dir=run_dir,
        )
        exp_h = Export(id=str(uuid.uuid4())[:12], run_id=run.id,
                       format="handoff_json", file_path=handoff_path)
        db.create_export(exp_h)
        export_records.append(exp_h)

        # ── Upload to Google Drive ────────────────────────────────────────────
        from drive_uploader import DRIVE_ENABLED, upload_run_exports
        if DRIVE_ENABLED:
            drive_results = upload_run_exports(export_records, monitor.project_id, monitor_id)
            for exp in export_records:
                info = drive_results.get(exp.id)
                if info:
                    db.update_export_drive(
                        exp.id,
                        info["file_id"],
                        info["web_view_link"],
                        info["download_link"],
                    )
                    exp.drive_file_id       = info["file_id"]
                    exp.drive_web_view_link = info["web_view_link"]
                    exp.drive_download_link = info["download_link"]
                    logger.debug(f"Drive: {exp.format} → {info['web_view_link']}")

            # Optional cleanup of local files after successful upload
            if CLEANUP_LOCAL:
                for exp in export_records:
                    if exp.drive_file_id and exp.file_path and os.path.exists(exp.file_path):
                        os.remove(exp.file_path)
                        logger.debug(f"Deleted local: {exp.file_path}")

        # ── Determine final status ────────────────────────────────────────────
        small = (len(posts) < SMALL_DATASET_MIN_POSTS or
                 len(comments) < SMALL_DATASET_MIN_COMMENTS)
        quality_status  = "small_dataset" if small else "ok"
        warning_msg     = (
            f"Small dataset: {len(posts)} posts / {len(comments)} comments. "
            "Try broader preset, lower thresholds, or longer period."
        ) if small else None

        run.status            = RUN_COMPLETED_WARNING if small else RUN_COMPLETED
        run.finished_at       = _utc_now()
        run.total_posts       = len(posts)
        run.total_comments    = len(comments)
        run.quality_status    = quality_status
        run.warning_message   = warning_msg
        run.export_path       = run_dir
        run.handoff_json_path = handoff_path
        run.top_keywords_json = get_top_keywords_for_db(posts, n=10)
        db.update_run(run)

        logger.success(
            f"✓ Run {run.id} {run.status} — "
            f"{len(posts)} posts, {len(comments)} comments | {run_dir}"
        )
        return run

    except Exception as e:
        logger.exception(f"Run {run.id} failed: {e}")
        run.status        = RUN_FAILED
        run.finished_at   = _utc_now()
        run.error_message = str(e)[:500]
        db.update_run(run)
        return run
