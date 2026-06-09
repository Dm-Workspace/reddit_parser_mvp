"""
SQLite storage layer.
Uses raw sqlite3 — swap connection string / cursor for SQLAlchemy later.
All public methods return dataclass instances from storage.models.
"""
import sqlite3
import json
import os
from typing import List, Optional
from loguru import logger

from storage.models import Project, Monitor, Run, Export

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tracker.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            market TEXT DEFAULT '',
            default_output_language TEXT DEFAULT 'en',
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS monitors (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT DEFAULT 'reddit',
            subreddit_preset TEXT NOT NULL,
            keyword_preset TEXT NOT NULL,
            run_mode TEXT NOT NULL,
            schedule_cron TEXT DEFAULT '',
            timezone TEXT DEFAULT 'UTC',
            enabled INTEGER DEFAULT 1,
            export_formats TEXT DEFAULT '["xlsx","json"]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            monitor_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            started_at TEXT,
            finished_at TEXT,
            total_posts INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            export_path TEXT,
            handoff_json_path TEXT,
            error_message TEXT,
            FOREIGN KEY (monitor_id) REFERENCES monitors(id)
        );

        CREATE TABLE IF NOT EXISTS exports (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            format TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );
        """)
    conn.close()
    logger.debug(f"DB initialised: {DB_PATH}")


# ─── Projects ─────────────────────────────────────────────────────────────────

def upsert_project(p: Project) -> None:
    conn = _get_conn()
    with conn:
        conn.execute("""
            INSERT INTO projects (id, name, description, language, market, default_output_language, enabled)
            VALUES (:id,:name,:description,:language,:market,:default_output_language,:enabled)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                language=excluded.language, market=excluded.market,
                default_output_language=excluded.default_output_language,
                enabled=excluded.enabled
        """, {"id": p.id, "name": p.name, "description": p.description,
              "language": p.language, "market": p.market,
              "default_output_language": p.default_output_language,
              "enabled": int(p.enabled)})
    conn.close()


def get_project(project_id: str) -> Optional[Project]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return Project(**{k: row[k] for k in row.keys() if k != "enabled"},
                   enabled=bool(row["enabled"]))


# ─── Monitors ─────────────────────────────────────────────────────────────────

def upsert_monitor(m: Monitor) -> None:
    conn = _get_conn()
    with conn:
        conn.execute("""
            INSERT INTO monitors
                (id, project_id, name, source, subreddit_preset, keyword_preset,
                 run_mode, schedule_cron, timezone, enabled, export_formats, updated_at)
            VALUES
                (:id,:project_id,:name,:source,:subreddit_preset,:keyword_preset,
                 :run_mode,:schedule_cron,:timezone,:enabled,:export_formats,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                project_id=excluded.project_id, name=excluded.name,
                subreddit_preset=excluded.subreddit_preset, keyword_preset=excluded.keyword_preset,
                run_mode=excluded.run_mode, schedule_cron=excluded.schedule_cron,
                timezone=excluded.timezone, enabled=excluded.enabled,
                export_formats=excluded.export_formats,
                updated_at=datetime('now')
        """, {"id": m.id, "project_id": m.project_id, "name": m.name,
              "source": m.source, "subreddit_preset": m.subreddit_preset,
              "keyword_preset": m.keyword_preset, "run_mode": m.run_mode,
              "schedule_cron": m.schedule_cron, "timezone": m.timezone,
              "enabled": int(m.enabled), "export_formats": m.export_formats})
    conn.close()


def get_monitor(monitor_id: str) -> Optional[Monitor]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM monitors WHERE id=?", (monitor_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["enabled"] = bool(d["enabled"])
    return Monitor(**d)


def list_monitors(enabled_only: bool = False) -> List[Monitor]:
    conn = _get_conn()
    q = "SELECT * FROM monitors"
    if enabled_only:
        q += " WHERE enabled=1"
    q += " ORDER BY project_id, id"
    rows = conn.execute(q).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        result.append(Monitor(**d))
    return result


def get_active_run_for_monitor(monitor_id: str) -> Optional[Run]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM runs WHERE monitor_id=? AND status IN ('queued','running') ORDER BY started_at DESC LIMIT 1",
        (monitor_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return Run(**dict(row))


# ─── Runs ──────────────────────────────────────────────────────────────────────

def create_run(run: Run) -> None:
    conn = _get_conn()
    with conn:
        conn.execute("""
            INSERT INTO runs (id, monitor_id, project_id, status, started_at)
            VALUES (:id,:monitor_id,:project_id,:status,:started_at)
        """, {"id": run.id, "monitor_id": run.monitor_id,
              "project_id": run.project_id, "status": run.status,
              "started_at": run.started_at})
    conn.close()


def update_run(run: Run) -> None:
    conn = _get_conn()
    with conn:
        conn.execute("""
            UPDATE runs SET
                status=:status, finished_at=:finished_at,
                total_posts=:total_posts, total_comments=:total_comments,
                export_path=:export_path, handoff_json_path=:handoff_json_path,
                error_message=:error_message
            WHERE id=:id
        """, {"id": run.id, "status": run.status, "finished_at": run.finished_at,
              "total_posts": run.total_posts, "total_comments": run.total_comments,
              "export_path": run.export_path, "handoff_json_path": run.handoff_json_path,
              "error_message": run.error_message})
    conn.close()


def list_runs(limit: int = 20, monitor_id: str = None) -> List[Run]:
    conn = _get_conn()
    if monitor_id:
        rows = conn.execute(
            "SELECT * FROM runs WHERE monitor_id=? ORDER BY started_at DESC LIMIT ?",
            (monitor_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [Run(**dict(row)) for row in rows]


# ─── Exports ──────────────────────────────────────────────────────────────────

def create_export(export: Export) -> None:
    conn = _get_conn()
    with conn:
        conn.execute("""
            INSERT INTO exports (id, run_id, format, file_path)
            VALUES (:id,:run_id,:format,:file_path)
        """, {"id": export.id, "run_id": export.run_id,
              "format": export.format, "file_path": export.file_path})
    conn.close()


def list_exports_for_run(run_id: str) -> List[Export]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM exports WHERE run_id=? ORDER BY created_at", (run_id,)
    ).fetchall()
    conn.close()
    return [Export(**dict(row)) for row in rows]
