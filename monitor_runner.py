"""
Monitor Runner
Executes a single monitor run end-to-end:
  1. Load monitor + project from DB
  2. Create run record
  3. Parse Reddit
  4. Export files
  5. Write AI handoff JSON
  6. Update run record
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
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
from storage.models import RUN_RUNNING, RUN_COMPLETED, RUN_COMPLETED_WARNING, RUN_FAILED


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _load_project(monitor: Monitor) -> Optional[Project]:
    project = db.get_project(monitor.project_id)
    if not project:
        logger.warning(f"Project '{monitor.project_id}' not found in DB, using defaults")
        from storage.models import Project
        project = Project(
            id=monitor.project_id, name=monitor.project_id,
            description="", language="en", market="",
            default_output_language="en", enabled=True,
        )
    return project


def run_monitor(monitor_id: str, dry_run: bool = False) -> Optional[Run]:
    """Execute a full monitor run. Returns the Run record."""
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        logger.error(f"Monitor '{monitor_id}' not found in DB. Run 'list-monitors' first.")
        return None

    if not monitor.enabled:
        logger.warning(f"Monitor '{monitor_id}' is disabled, skipping")
        return None

    # Guard: don't run if already running
    active = db.get_active_run_for_monitor(monitor_id)
    if active:
        logger.warning(f"Monitor '{monitor_id}' already has an active run ({active.id}), skipping")
        return active

    project = _load_project(monitor)
    run_id = str(uuid.uuid4())[:12]
    run = Run(
        id=run_id,
        monitor_id=monitor_id,
        project_id=monitor.project_id,
        status=RUN_RUNNING,
        started_at=_now(),
    )
    db.create_run(run)
    logger.info(f"▶ Run {run_id} started — monitor: {monitor.name}")

    if dry_run:
        logger.info("Dry run mode — skipping actual parsing")
        run.status = RUN_COMPLETED
        run.finished_at = _now()
        db.update_run(run)
        return run

    try:
        # Resolve settings from run_mode
        mode_cfg = RUN_MODES.get(monitor.run_mode, {})
        sort = mode_cfg.get("sort", "hot")
        period = mode_cfg.get("period", "last_7d")
        limit = mode_cfg.get("limit", 50)
        max_comments = mode_cfg.get("comments", 20)
        min_score = mode_cfg.get("min_score", 3)
        min_comments_count = mode_cfg.get("min_comments", 5)

        keywords = KEYWORD_PRESETS.get(monitor.keyword_preset, [])
        subreddits = SUBREDDIT_PRESETS.get(monitor.subreddit_preset, [])

        # Auto language mode
        EN_PRESETS = {"wellness_en", "crm_en", "ai_en"}
        language_mode = "en" if monitor.keyword_preset in EN_PRESETS else "mixed"

        run_settings = {
            "run_date": now_utc_str(),
            "run_id": run_id,
            "monitor_id": monitor_id,
            "monitor_name": monitor.name,
            "project_id": monitor.project_id,
            "subreddits": ", ".join(subreddits),
            "subreddit_preset": monitor.subreddit_preset,
            "keywords": ", ".join(keywords) if keywords else "all",
            "keyword_preset": monitor.keyword_preset,
            "period": period,
            "sort": sort,
            "run_mode": monitor.run_mode,
            "limit_per_subreddit": limit,
            "max_comments_per_post": max_comments,
            "min_score": min_score,
            "min_comments": min_comments_count,
            "language_mode": language_mode,
            "filter_bots": True,
            "fetch_selftext": True,
            "export_format": json.loads(monitor.export_formats),
        }

        # Parse
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
                min_comments=min_comments_count,
                language_mode=language_mode,
            )
        finally:
            close_reddit_client(reddit)

        posts = deduplicate_posts(posts)
        comments = deduplicate_comments(comments)
        logger.info(f"Collected: {len(posts)} posts, {len(comments)} comments")

        # Output directory per run
        run_dir = os.path.join(
            EXPORTS_DIR,
            monitor.project_id,
            monitor_id,
            run_id,
        )
        os.makedirs(run_dir, exist_ok=True)

        export_formats = json.loads(monitor.export_formats)
        export_paths = []

        if "xlsx" in export_formats:
            from exporters.excel_exporter import export_excel
            xlsx_path = os.path.join(run_dir, f"report_{now_file_str()}.xlsx")
            export_excel(posts, comments, run_settings, xlsx_path,
                         all_subreddits=subreddits)
            export_paths.append(xlsx_path)
            db.create_export(Export(
                id=str(uuid.uuid4())[:12], run_id=run_id,
                format="xlsx", file_path=xlsx_path,
            ))

        if "csv" in export_formats:
            from exporters.csv_exporter import export_csv
            prefix = os.path.join(run_dir, f"report_{now_file_str()}")
            posts_path, comments_path = export_csv(posts, comments, prefix)
            for path in [posts_path, comments_path]:
                export_paths.append(path)
                db.create_export(Export(
                    id=str(uuid.uuid4())[:12], run_id=run_id,
                    format="csv", file_path=path,
                ))

        if "json" in export_formats:
            from exporters.json_exporter import export_json
            json_path = os.path.join(run_dir, f"report_{now_file_str()}.json")
            export_json(posts, comments, run_settings, json_path)
            export_paths.append(json_path)
            db.create_export(Export(
                id=str(uuid.uuid4())[:12], run_id=run_id,
                format="json", file_path=json_path,
            ))

        # Handoff JSON (always written)
        from exporters.handoff_exporter import export_handoff
        handoff_path = export_handoff(
            posts=posts, comments=comments,
            run=run, monitor=monitor, project=project,
            run_settings=run_settings, output_dir=run_dir,
        )
        db.create_export(Export(
            id=str(uuid.uuid4())[:12], run_id=run_id,
            format="handoff_json", file_path=handoff_path,
        ))

        # Determine final status
        small = (len(posts) < SMALL_DATASET_MIN_POSTS or
                 len(comments) < SMALL_DATASET_MIN_COMMENTS)
        final_status = RUN_COMPLETED_WARNING if small else RUN_COMPLETED
        if small:
            logger.warning(f"Small dataset: {len(posts)} posts / {len(comments)} comments")

        run.status = final_status
        run.finished_at = _now()
        run.total_posts = len(posts)
        run.total_comments = len(comments)
        run.export_path = run_dir
        run.handoff_json_path = handoff_path
        db.update_run(run)

        logger.success(f"✓ Run {run_id} {final_status} — {len(posts)} posts, {len(comments)} comments")
        logger.success(f"  Export dir: {run_dir}")
        return run

    except Exception as e:
        logger.exception(f"Run {run_id} failed: {e}")
        run.status = RUN_FAILED
        run.finished_at = _now()
        run.error_message = str(e)
        db.update_run(run)
        return run
