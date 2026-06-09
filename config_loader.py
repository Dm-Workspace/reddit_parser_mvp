"""
Loads monitors.yaml and syncs projects/monitors into SQLite.
"""
import json
import os
from typing import List, Dict, Any
import yaml
from loguru import logger

from storage import database as db
from storage.models import Project, Monitor

MONITORS_YAML = os.path.join(os.path.dirname(__file__), "monitors.yaml")


def load_yaml() -> Dict[str, Any]:
    if not os.path.exists(MONITORS_YAML):
        logger.warning(f"monitors.yaml not found at {MONITORS_YAML}")
        return {}
    with open(MONITORS_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sync_to_db() -> tuple[List[Project], List[Monitor]]:
    """Read monitors.yaml and upsert all projects/monitors into DB."""
    db.init_db()
    data = load_yaml()

    projects = []
    for p in data.get("projects", []):
        project = Project(
            id=p["id"],
            name=p.get("name", p["id"]),
            description=p.get("description", ""),
            language=p.get("language", "en"),
            market=p.get("market", ""),
            default_output_language=p.get("default_output_language", "en"),
            enabled=p.get("enabled", True),
        )
        db.upsert_project(project)
        projects.append(project)

    monitors = []
    for m in data.get("monitors", []):
        fmt = m.get("export_formats", ["xlsx", "json"])
        monitor = Monitor(
            id=m["id"],
            project_id=m["project_id"],
            name=m.get("name", m["id"]),
            source=m.get("source", "reddit"),
            subreddit_preset=m["subreddit_preset"],
            keyword_preset=m["keyword_preset"],
            run_mode=m["run_mode"],
            schedule_cron=m.get("schedule_cron", ""),
            timezone=m.get("timezone", "UTC"),
            enabled=m.get("enabled", True),
            export_formats=json.dumps(fmt),
        )
        db.upsert_monitor(monitor)
        monitors.append(monitor)

    logger.info(f"Synced {len(projects)} projects, {len(monitors)} monitors from monitors.yaml")
    return projects, monitors


def get_all_monitors(enabled_only: bool = True) -> List[Monitor]:
    sync_to_db()
    return db.list_monitors(enabled_only=enabled_only)


def get_monitor_by_id(monitor_id: str) -> Monitor:
    sync_to_db()
    return db.get_monitor(monitor_id)
