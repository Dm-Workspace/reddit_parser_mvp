"""
Dataclass models for all DB entities.
Dual backend: Postgres (DATABASE_URL) or SQLite fallback.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Users ──────────────────────────────────────────────────────────────────────

@dataclass
class User:
    telegram_id: int
    username: str               = ""
    first_name: str             = ""
    role: str                   = "user"   # user | admin
    created_at: str             = ""
    updated_at: str             = ""


# ── Projects ───────────────────────────────────────────────────────────────────

@dataclass
class Project:
    id: str
    name: str
    owner_telegram_id: int      = 0
    description: str            = ""
    niche: str                  = ""
    target_market: str          = ""
    output_language: str        = "en"     # ru | en | uk
    enabled: bool               = True
    archived: bool              = False
    created_at: str             = ""
    updated_at: str             = ""

    # Legacy compatibility fields (kept for monitors.yaml loading)
    language: str               = "en"
    market: str                 = ""
    default_output_language: str = "en"


# ── Monitors ───────────────────────────────────────────────────────────────────

@dataclass
class Monitor:
    id: str
    project_id: str
    name: str
    owner_telegram_id: int      = 0
    description: str            = ""
    source: str                 = "reddit"

    # Presets (DB IDs or legacy config keys)
    subreddit_preset_id: Optional[str]  = None
    keyword_preset_id: Optional[str]    = None
    custom_subreddits: str              = "[]"   # JSON list
    custom_keywords: str                = "[]"   # JSON list

    run_mode: str               = "hot_last_7d"

    # Scheduling
    schedule_mode: str          = "manual"     # manual | scheduled | disabled
    frequency: str              = "none"       # none | weekly | biweekly | monthly | custom_cron
    schedule_cron: str          = ""
    next_run_at: Optional[str]  = None
    timezone: str               = "UTC"
    last_run_at: Optional[str]  = None

    # Limits & safety
    min_days_between_runs: int  = 7
    max_runs_per_month: int     = 4
    require_manual_confirmation: bool = True

    enabled: bool               = True
    archived: bool              = False
    export_formats: str         = '["xlsx","json"]'

    created_at: str             = ""
    updated_at: str             = ""


# ── Presets ────────────────────────────────────────────────────────────────────

@dataclass
class SubredditPreset:
    id: str
    name: str
    subreddits: str             = "[]"   # JSON list
    description: str            = ""
    owner_telegram_id: int      = 0      # 0 = system preset
    project_id: Optional[str]   = None
    is_system: bool             = False
    created_at: str             = ""
    updated_at: str             = ""


@dataclass
class KeywordPreset:
    id: str
    name: str
    keywords: str               = "[]"   # JSON list
    description: str            = ""
    language: str               = "en"
    owner_telegram_id: int      = 0
    project_id: Optional[str]   = None
    is_system: bool             = False
    created_at: str             = ""
    updated_at: str             = ""


# ── Run statuses ───────────────────────────────────────────────────────────────

RUN_QUEUED            = "queued"
RUN_RUNNING           = "running"
RUN_COMPLETED         = "completed"
RUN_COMPLETED_WARNING = "completed_with_warning"
RUN_FAILED            = "failed"


@dataclass
class Run:
    id: str
    monitor_id: str
    project_id: str
    status: str
    started_at: str
    owner_telegram_id: int           = 0
    finished_at: Optional[str]       = None
    total_posts: int                 = 0
    total_comments: int              = 0
    quality_status: str              = "ok"
    warning_message: Optional[str]  = None
    error_message: Optional[str]    = None
    export_path: Optional[str]      = None
    handoff_json_path: Optional[str] = None
    top_keywords_json: Optional[str] = None
    created_at: str                  = ""
    updated_at: str                  = ""


@dataclass
class Export:
    id: str
    run_id: str
    format: str
    file_path: str                        = ""
    owner_telegram_id: int                = 0
    project_id: str                       = ""
    monitor_id: str                       = ""
    file_name: str                        = ""
    file_size: Optional[int]              = None
    drive_file_id: Optional[str]          = None
    drive_web_view_link: Optional[str]    = None
    drive_download_link: Optional[str]    = None
    created_at: str                       = ""


# ── Limits ─────────────────────────────────────────────────────────────────────

MAX_ACTIVE_PROJECTS_PER_USER    = int(__import__("os").environ.get("MAX_ACTIVE_PROJECTS_PER_USER", "3"))
MAX_ACTIVE_MONITORS_PER_PROJECT = int(__import__("os").environ.get("MAX_ACTIVE_MONITORS_PER_PROJECT", "5"))
MAX_MANUAL_RUNS_PER_DAY         = int(__import__("os").environ.get("MAX_MANUAL_RUNS_PER_DAY", "5"))
MAX_TOTAL_RUNS_PER_MONTH        = int(__import__("os").environ.get("MAX_TOTAL_RUNS_PER_MONTH", "30"))

APP_VERSION = "6.1"
