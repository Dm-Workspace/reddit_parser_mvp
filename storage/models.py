"""
Dataclass models for DB entities.
Designed to map 1:1 to SQLite tables.
Easy to swap for SQLAlchemy/Postgres later.
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Project:
    id: str
    name: str
    description: str
    language: str
    market: str
    default_output_language: str
    enabled: bool
    created_at: str = ""


@dataclass
class Monitor:
    id: str
    project_id: str
    name: str
    source: str
    subreddit_preset: str
    keyword_preset: str
    run_mode: str
    schedule_cron: str
    timezone: str
    enabled: bool
    export_formats: str  # JSON-encoded list, e.g. '["xlsx","json"]'
    created_at: str = ""
    updated_at: str = ""


# Run statuses
RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_COMPLETED_WARNING = "completed_with_warning"
RUN_FAILED = "failed"


@dataclass
class Run:
    id: str
    monitor_id: str
    project_id: str
    status: str
    started_at: str
    finished_at: Optional[str] = None
    total_posts: int = 0
    total_comments: int = 0
    export_path: Optional[str] = None
    handoff_json_path: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class Export:
    id: str
    run_id: str
    format: str
    file_path: str
    created_at: str = ""
