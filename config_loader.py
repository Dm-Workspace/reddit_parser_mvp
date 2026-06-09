"""
Config loader:
1. Seeds system presets (subreddit + keyword) to DB on startup.
2. Optionally syncs monitors.yaml (for power-users / backward compat).

User projects and monitors are created via Telegram — NOT hardcoded here.
"""
import json
import os
from typing import List

import yaml
from loguru import logger

from storage import database as db
from storage.models import SubredditPreset, KeywordPreset, Project, Monitor

MONITORS_YAML = os.path.join(os.path.dirname(__file__), "monitors.yaml")


# ── System presets (from config.py) ───────────────────────────────────────────

def seed_system_presets() -> None:
    """Insert/update all system presets into DB. Safe to call on every startup."""
    db.init_db()
    from config import SUBREDDIT_PRESETS, KEYWORD_PRESETS

    for preset_id, subs in SUBREDDIT_PRESETS.items():
        p = SubredditPreset(
            id=preset_id,
            name=preset_id.replace("_", " ").title(),
            subreddits=json.dumps(subs),
            description=f"System preset: {len(subs)} subreddits",
            owner_telegram_id=0,
            project_id=None,
            is_system=True,
        )
        db.upsert_subreddit_preset(p)

    for preset_id, kws in KEYWORD_PRESETS.items():
        lang = "ru" if "ru" in preset_id else ("uk" if "uk" in preset_id else "en")
        p = KeywordPreset(
            id=preset_id,
            name=preset_id.replace("_", " ").title(),
            keywords=json.dumps(kws),
            description=f"System preset: {len(kws)} keywords",
            language=lang,
            owner_telegram_id=0,
            project_id=None,
            is_system=True,
        )
        db.upsert_keyword_preset(p)

    logger.info("System presets seeded to DB")


# ── monitors.yaml (backward compat / power users) ─────────────────────────────

def _load_yaml() -> dict:
    if not os.path.exists(MONITORS_YAML):
        return {}
    with open(MONITORS_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sync_monitors_yaml() -> None:
    """
    Load monitors.yaml and upsert projects/monitors into DB.
    Called on startup — safe to call multiple times.
    Projects from yaml get owner_telegram_id=0 (system/unowned).
    """
    db.init_db()
    data = _load_yaml()
    if not data:
        return

    for p in data.get("projects", []):
        project = Project(
            id=p["id"],
            owner_telegram_id=0,
            name=p.get("name", p["id"]),
            description=p.get("description", ""),
            niche=p.get("market", ""),
            target_market=p.get("market", ""),
            output_language=p.get("default_output_language", "en"),
            enabled=p.get("enabled", True),
            archived=False,
        )
        db.upsert_project(project)

    for m in data.get("monitors", []):
        fmt = m.get("export_formats", ["xlsx", "json"])
        # Map old subreddit_preset / keyword_preset fields to new IDs
        sr_preset = m.get("subreddit_preset") or m.get("subreddit_preset_id")
        kw_preset = m.get("keyword_preset") or m.get("keyword_preset_id")

        schedule_cron = m.get("schedule_cron", "")
        schedule_mode = "scheduled" if schedule_cron else "manual"

        monitor = Monitor(
            id=m["id"],
            project_id=m["project_id"],
            owner_telegram_id=0,
            name=m.get("name", m["id"]),
            description=m.get("description", ""),
            source=m.get("source", "reddit"),
            subreddit_preset_id=sr_preset,
            keyword_preset_id=kw_preset,
            custom_subreddits="[]",
            custom_keywords="[]",
            run_mode=m.get("run_mode", "hot_last_7d"),
            schedule_mode=schedule_mode,
            frequency=_cron_to_frequency(schedule_cron),
            schedule_cron=schedule_cron,
            timezone=m.get("timezone", "UTC"),
            enabled=m.get("enabled", True),
            archived=False,
            export_formats=json.dumps(fmt if isinstance(fmt, list) else [fmt]),
        )
        db.upsert_monitor(monitor)

    logger.info(f"monitors.yaml synced: {len(data.get('projects', []))} projects, "
                f"{len(data.get('monitors', []))} monitors")


def _cron_to_frequency(cron: str) -> str:
    """Guess frequency from cron expression."""
    if not cron:
        return "none"
    parts = cron.split()
    if len(parts) != 5:
        return "custom_cron"
    # monthly: "0 10 1 * *"
    if parts[2] != "*" and parts[4] == "*":
        return "monthly"
    # weekly: "0 8 * * 1"
    if parts[4] != "*":
        return "weekly"
    return "custom_cron"


# ── Legacy functions (kept for backward compat with main.py / scheduler) ──────

def sync_to_db():
    """Deprecated alias for seed_system_presets + sync_monitors_yaml."""
    seed_system_presets()
    sync_monitors_yaml()


def get_all_monitors(enabled_only: bool = True) -> List[Monitor]:
    sync_to_db()
    return db.list_monitors(enabled_only=enabled_only)


def get_monitor_by_id(monitor_id: str) -> Monitor:
    sync_to_db()
    return db.get_monitor(monitor_id)
