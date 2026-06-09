"""
Dual-backend storage: Postgres (DATABASE_URL) or SQLite fallback.
All SQL uses ? placeholders — auto-replaced with %s for Postgres.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
from storage.models import (
    User, Project, Monitor, SubredditPreset, KeywordPreset,
    Run, Export,
    MAX_ACTIVE_PROJECTS_PER_USER, MAX_ACTIVE_MONITORS_PER_PROJECT,
)

# ── Backend detection ──────────────────────────────────────────────────────────
_DB_URL    = os.environ.get("DATABASE_URL", "")
_USE_PG    = _DB_URL.startswith(("postgres://", "postgresql://"))
_PH        = "%s" if _USE_PG else "?"
_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tracker.db")


def _get_conn():
    if _USE_PG:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(_DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        return conn
    os.makedirs(os.path.dirname(_SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _exec(conn, sql: str, params: tuple = ()):
    sql = sql.replace("?", _PH)
    if _USE_PG:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur
    return conn.execute(sql, params)


def _rows(conn, sql: str, params: tuple = ()) -> List[dict]:
    cur = _exec(conn, sql, params)
    return [dict(r) for r in (cur.fetchall() or [])]


def _one(conn, sql: str, params: tuple = ()) -> Optional[dict]:
    r = _rows(conn, sql, params)
    return r[0] if r else None


def _commit(conn):
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Schema ─────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id  BIGINT PRIMARY KEY,
    username     TEXT DEFAULT '',
    first_name   TEXT DEFAULT '',
    role         TEXT DEFAULT 'user',
    created_at   TEXT,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id                     TEXT PRIMARY KEY,
    owner_telegram_id      BIGINT DEFAULT 0,
    name                   TEXT NOT NULL,
    description            TEXT DEFAULT '',
    niche                  TEXT DEFAULT '',
    target_market          TEXT DEFAULT '',
    output_language        TEXT DEFAULT 'en',
    enabled                INTEGER DEFAULT 1,
    archived               INTEGER DEFAULT 0,
    created_at             TEXT,
    updated_at             TEXT
);

CREATE TABLE IF NOT EXISTS monitors (
    id                          TEXT PRIMARY KEY,
    project_id                  TEXT NOT NULL,
    owner_telegram_id           BIGINT DEFAULT 0,
    name                        TEXT NOT NULL,
    description                 TEXT DEFAULT '',
    source                      TEXT DEFAULT 'reddit',
    subreddit_preset_id         TEXT,
    keyword_preset_id           TEXT,
    custom_subreddits           TEXT DEFAULT '[]',
    custom_keywords             TEXT DEFAULT '[]',
    run_mode                    TEXT DEFAULT 'hot_last_7d',
    schedule_mode               TEXT DEFAULT 'manual',
    frequency                   TEXT DEFAULT 'none',
    schedule_cron               TEXT DEFAULT '',
    next_run_at                 TEXT,
    timezone                    TEXT DEFAULT 'UTC',
    last_run_at                 TEXT,
    min_days_between_runs       INTEGER DEFAULT 7,
    max_runs_per_month          INTEGER DEFAULT 4,
    require_manual_confirmation INTEGER DEFAULT 1,
    enabled                     INTEGER DEFAULT 1,
    archived                    INTEGER DEFAULT 0,
    export_formats              TEXT DEFAULT '["xlsx","json"]',
    created_at                  TEXT,
    updated_at                  TEXT
);

CREATE TABLE IF NOT EXISTS subreddit_presets (
    id                TEXT PRIMARY KEY,
    owner_telegram_id BIGINT DEFAULT 0,
    project_id        TEXT,
    name              TEXT NOT NULL,
    description       TEXT DEFAULT '',
    subreddits        TEXT DEFAULT '[]',
    is_system         INTEGER DEFAULT 0,
    created_at        TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS keyword_presets (
    id                TEXT PRIMARY KEY,
    owner_telegram_id BIGINT DEFAULT 0,
    project_id        TEXT,
    name              TEXT NOT NULL,
    description       TEXT DEFAULT '',
    keywords          TEXT DEFAULT '[]',
    language          TEXT DEFAULT 'en',
    is_system         INTEGER DEFAULT 0,
    created_at        TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id                TEXT PRIMARY KEY,
    monitor_id        TEXT NOT NULL,
    project_id        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'queued',
    started_at        TEXT,
    finished_at       TEXT,
    total_posts       INTEGER DEFAULT 0,
    total_comments    INTEGER DEFAULT 0,
    quality_status    TEXT DEFAULT 'ok',
    warning_message   TEXT,
    error_message     TEXT,
    export_path       TEXT,
    handoff_json_path TEXT,
    top_keywords_json TEXT
);

CREATE TABLE IF NOT EXISTS exports (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL,
    format              TEXT NOT NULL,
    file_path           TEXT DEFAULT '',
    drive_file_id       TEXT,
    drive_web_view_link TEXT,
    drive_download_link TEXT,
    created_at          TEXT
);
"""

_MIGRATIONS_PG = [
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS owner_telegram_id BIGINT DEFAULT 0",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS subreddit_preset_id TEXT",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS keyword_preset_id TEXT",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS custom_subreddits TEXT DEFAULT '[]'",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS custom_keywords TEXT DEFAULT '[]'",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS schedule_mode TEXT DEFAULT 'manual'",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS frequency TEXT DEFAULT 'none'",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS next_run_at TEXT",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS last_run_at TEXT",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS min_days_between_runs INTEGER DEFAULT 7",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS max_runs_per_month INTEGER DEFAULT 4",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS require_manual_confirmation INTEGER DEFAULT 1",
    "ALTER TABLE monitors ADD COLUMN IF NOT EXISTS archived INTEGER DEFAULT 0",
    "ALTER TABLE projects  ADD COLUMN IF NOT EXISTS owner_telegram_id BIGINT DEFAULT 0",
    "ALTER TABLE projects  ADD COLUMN IF NOT EXISTS niche TEXT DEFAULT ''",
    "ALTER TABLE projects  ADD COLUMN IF NOT EXISTS target_market TEXT DEFAULT ''",
    "ALTER TABLE projects  ADD COLUMN IF NOT EXISTS output_language TEXT DEFAULT 'en'",
    "ALTER TABLE projects  ADD COLUMN IF NOT EXISTS archived INTEGER DEFAULT 0",
    "ALTER TABLE projects  ADD COLUMN IF NOT EXISTS updated_at TEXT",
    "ALTER TABLE runs      ADD COLUMN IF NOT EXISTS quality_status TEXT DEFAULT 'ok'",
    "ALTER TABLE runs      ADD COLUMN IF NOT EXISTS warning_message TEXT",
    "ALTER TABLE runs      ADD COLUMN IF NOT EXISTS top_keywords_json TEXT",
    "ALTER TABLE exports   ADD COLUMN IF NOT EXISTS drive_file_id TEXT",
    "ALTER TABLE exports   ADD COLUMN IF NOT EXISTS drive_web_view_link TEXT",
    "ALTER TABLE exports   ADD COLUMN IF NOT EXISTS drive_download_link TEXT",
]

_MIGRATIONS_SQLITE = [
    ("monitors", "owner_telegram_id",           "INTEGER DEFAULT 0"),
    ("monitors", "description",                 "TEXT DEFAULT ''"),
    ("monitors", "subreddit_preset_id",         "TEXT"),
    ("monitors", "keyword_preset_id",           "TEXT"),
    ("monitors", "custom_subreddits",           "TEXT DEFAULT '[]'"),
    ("monitors", "custom_keywords",             "TEXT DEFAULT '[]'"),
    ("monitors", "schedule_mode",               "TEXT DEFAULT 'manual'"),
    ("monitors", "frequency",                   "TEXT DEFAULT 'none'"),
    ("monitors", "next_run_at",                 "TEXT"),
    ("monitors", "last_run_at",                 "TEXT"),
    ("monitors", "min_days_between_runs",       "INTEGER DEFAULT 7"),
    ("monitors", "max_runs_per_month",          "INTEGER DEFAULT 4"),
    ("monitors", "require_manual_confirmation", "INTEGER DEFAULT 1"),
    ("monitors", "archived",                    "INTEGER DEFAULT 0"),
    ("projects", "owner_telegram_id",           "INTEGER DEFAULT 0"),
    ("projects", "niche",                       "TEXT DEFAULT ''"),
    ("projects", "target_market",               "TEXT DEFAULT ''"),
    ("projects", "output_language",             "TEXT DEFAULT 'en'"),
    ("projects", "archived",                    "INTEGER DEFAULT 0"),
    ("projects", "updated_at",                  "TEXT"),
    ("runs",     "quality_status",              "TEXT DEFAULT 'ok'"),
    ("runs",     "warning_message",             "TEXT"),
    ("runs",     "top_keywords_json",           "TEXT"),
    ("exports",  "drive_file_id",               "TEXT"),
    ("exports",  "drive_web_view_link",         "TEXT"),
    ("exports",  "drive_download_link",         "TEXT"),
]


def init_db() -> None:
    conn = _get_conn()
    try:
        if _USE_PG:
            cur = conn.cursor()
            for stmt in _SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
            for sql in _MIGRATIONS_PG:
                try:
                    cur.execute(sql)
                except Exception:
                    pass
        else:
            conn.executescript(_SCHEMA)
            for table, col, typedef in _MIGRATIONS_SQLITE:
                try:
                    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                    if col not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
        _commit(conn)
        logger.debug(f"DB ready ({'postgres' if _USE_PG else _SQLITE_PATH})")
    finally:
        conn.close()


# ── Helpers for dataclass <-> dict ─────────────────────────────────────────────

def _to_model(cls, row: dict):
    fields = cls.__dataclass_fields__
    data = {k: row[k] for k in fields if k in row}
    for bool_field in ("enabled", "archived", "is_system", "require_manual_confirmation"):
        if bool_field in data:
            data[bool_field] = bool(data[bool_field])
    return cls(**data)


# ── Users ──────────────────────────────────────────────────────────────────────

def upsert_user(u: User) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO users (telegram_id,username,first_name,role,created_at,updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username, first_name=excluded.first_name,
                updated_at=excluded.updated_at
        """, (u.telegram_id, u.username, u.first_name, u.role,
              u.created_at or _now(), _now()))
        _commit(conn)
    finally:
        conn.close()


def get_user(telegram_id: int) -> Optional[User]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        return _to_model(User, row) if row else None
    finally:
        conn.close()


# ── Projects ───────────────────────────────────────────────────────────────────

def create_project(p: Project) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO projects
                (id,owner_telegram_id,name,description,niche,target_market,
                 output_language,enabled,archived,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (p.id, p.owner_telegram_id, p.name, p.description, p.niche,
              p.target_market, p.output_language, int(p.enabled), int(p.archived),
              p.created_at or _now(), _now()))
        _commit(conn)
    finally:
        conn.close()


def update_project(p: Project) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            UPDATE projects SET
                name=?,description=?,niche=?,target_market=?,output_language=?,
                enabled=?,archived=?,updated_at=?
            WHERE id=?
        """, (p.name, p.description, p.niche, p.target_market, p.output_language,
              int(p.enabled), int(p.archived), _now(), p.id))
        _commit(conn)
    finally:
        conn.close()


def upsert_project(p: Project) -> None:
    """Backward-compatible upsert (used by config_loader for system projects)."""
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO projects
                (id,owner_telegram_id,name,description,niche,target_market,
                 output_language,enabled,archived,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                niche=excluded.niche, target_market=excluded.target_market,
                output_language=excluded.output_language,
                enabled=excluded.enabled, updated_at=excluded.updated_at
        """, (p.id, p.owner_telegram_id, p.name, p.description, p.niche,
              p.target_market, p.output_language, int(p.enabled), int(p.archived),
              p.created_at or _now(), _now()))
        _commit(conn)
    finally:
        conn.close()


def get_project(project_id: str) -> Optional[Project]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
        return _to_model(Project, row) if row else None
    finally:
        conn.close()


def list_projects(
    owner_telegram_id: int = None,
    include_archived: bool = False,
) -> List[Project]:
    conn = _get_conn()
    try:
        conditions = []
        params = []
        if owner_telegram_id is not None:
            conditions.append("owner_telegram_id=?")
            params.append(owner_telegram_id)
        if not include_archived:
            conditions.append("archived=0")
        q = "SELECT * FROM projects"
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY created_at DESC"
        rows = _rows(conn, q, tuple(params))
        return [_to_model(Project, r) for r in rows]
    finally:
        conn.close()


def count_active_projects(owner_telegram_id: int) -> int:
    conn = _get_conn()
    try:
        row = _one(conn,
            "SELECT COUNT(*) as cnt FROM projects WHERE owner_telegram_id=? AND archived=0 AND enabled=1",
            (owner_telegram_id,))
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def archive_project(project_id: str) -> None:
    conn = _get_conn()
    try:
        _exec(conn, "UPDATE projects SET archived=1, updated_at=? WHERE id=?", (_now(), project_id))
        _commit(conn)
    finally:
        conn.close()


# ── Monitors ───────────────────────────────────────────────────────────────────

def _monitor_insert_params(m: Monitor) -> tuple:
    return (
        m.id, m.project_id, m.owner_telegram_id, m.name, m.description,
        m.source, m.subreddit_preset_id, m.keyword_preset_id,
        m.custom_subreddits, m.custom_keywords, m.run_mode,
        m.schedule_mode, m.frequency, m.schedule_cron, m.next_run_at,
        m.timezone, m.last_run_at, m.min_days_between_runs,
        m.max_runs_per_month, int(m.require_manual_confirmation),
        int(m.enabled), int(m.archived), m.export_formats,
        m.created_at or _now(), _now(),
    )


def create_monitor(m: Monitor) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO monitors
                (id,project_id,owner_telegram_id,name,description,source,
                 subreddit_preset_id,keyword_preset_id,custom_subreddits,custom_keywords,
                 run_mode,schedule_mode,frequency,schedule_cron,next_run_at,timezone,
                 last_run_at,min_days_between_runs,max_runs_per_month,
                 require_manual_confirmation,enabled,archived,export_formats,
                 created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, _monitor_insert_params(m))
        _commit(conn)
    finally:
        conn.close()


def update_monitor(m: Monitor) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            UPDATE monitors SET
                name=?,description=?,subreddit_preset_id=?,keyword_preset_id=?,
                custom_subreddits=?,custom_keywords=?,run_mode=?,
                schedule_mode=?,frequency=?,schedule_cron=?,next_run_at=?,
                timezone=?,last_run_at=?,min_days_between_runs=?,max_runs_per_month=?,
                require_manual_confirmation=?,enabled=?,archived=?,export_formats=?,
                updated_at=?
            WHERE id=?
        """, (m.name, m.description, m.subreddit_preset_id, m.keyword_preset_id,
              m.custom_subreddits, m.custom_keywords, m.run_mode,
              m.schedule_mode, m.frequency, m.schedule_cron, m.next_run_at,
              m.timezone, m.last_run_at, m.min_days_between_runs, m.max_runs_per_month,
              int(m.require_manual_confirmation), int(m.enabled), int(m.archived),
              m.export_formats, _now(), m.id))
        _commit(conn)
    finally:
        conn.close()


def upsert_monitor(m: Monitor) -> None:
    """Backward-compatible upsert (used by config_loader for monitors.yaml)."""
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO monitors
                (id,project_id,owner_telegram_id,name,description,source,
                 subreddit_preset_id,keyword_preset_id,custom_subreddits,custom_keywords,
                 run_mode,schedule_mode,frequency,schedule_cron,next_run_at,timezone,
                 last_run_at,min_days_between_runs,max_runs_per_month,
                 require_manual_confirmation,enabled,archived,export_formats,
                 created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                subreddit_preset_id=excluded.subreddit_preset_id,
                keyword_preset_id=excluded.keyword_preset_id,
                run_mode=excluded.run_mode, schedule_mode=excluded.schedule_mode,
                schedule_cron=excluded.schedule_cron, next_run_at=excluded.next_run_at,
                timezone=excluded.timezone, enabled=excluded.enabled,
                export_formats=excluded.export_formats, updated_at=excluded.updated_at
        """, _monitor_insert_params(m))
        _commit(conn)
    finally:
        conn.close()


def get_monitor(monitor_id: str) -> Optional[Monitor]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM monitors WHERE id=?", (monitor_id,))
        return _to_model(Monitor, row) if row else None
    finally:
        conn.close()


def list_monitors(
    project_id: str = None,
    owner_telegram_id: int = None,
    enabled_only: bool = False,
    include_archived: bool = False,
) -> List[Monitor]:
    conn = _get_conn()
    try:
        conditions, params = [], []
        if project_id:
            conditions.append("project_id=?"); params.append(project_id)
        if owner_telegram_id is not None:
            conditions.append("owner_telegram_id=?"); params.append(owner_telegram_id)
        if enabled_only:
            conditions.append("enabled=1")
        if not include_archived:
            conditions.append("archived=0")
        q = "SELECT * FROM monitors"
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY project_id, name"
        rows = _rows(conn, q, tuple(params))
        return [_to_model(Monitor, r) for r in rows]
    finally:
        conn.close()


def count_active_monitors(project_id: str) -> int:
    conn = _get_conn()
    try:
        row = _one(conn,
            "SELECT COUNT(*) as cnt FROM monitors WHERE project_id=? AND archived=0 AND enabled=1",
            (project_id,))
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def archive_monitor(monitor_id: str) -> None:
    conn = _get_conn()
    try:
        _exec(conn, "UPDATE monitors SET archived=1, updated_at=? WHERE id=?", (_now(), monitor_id))
        _commit(conn)
    finally:
        conn.close()


def get_active_run_for_monitor(monitor_id: str) -> Optional[Run]:
    conn = _get_conn()
    try:
        row = _one(conn,
            "SELECT * FROM runs WHERE monitor_id=? AND status IN ('queued','running') "
            "ORDER BY started_at DESC LIMIT 1", (monitor_id,))
        return _to_model(Run, row) if row else None
    finally:
        conn.close()


def get_due_monitors() -> List[Monitor]:
    """Return scheduled monitors whose next_run_at <= NOW."""
    conn = _get_conn()
    try:
        now = _now()
        rows = _rows(conn,
            "SELECT * FROM monitors WHERE schedule_mode='scheduled' "
            "AND enabled=1 AND archived=0 "
            "AND next_run_at IS NOT NULL AND next_run_at <= ?",
            (now,))
        return [_to_model(Monitor, r) for r in rows]
    finally:
        conn.close()


def update_monitor_after_run(monitor_id: str, last_run_at: str, next_run_at: Optional[str]) -> None:
    conn = _get_conn()
    try:
        _exec(conn,
            "UPDATE monitors SET last_run_at=?, next_run_at=?, updated_at=? WHERE id=?",
            (last_run_at, next_run_at, _now(), monitor_id))
        _commit(conn)
    finally:
        conn.close()


def get_queued_runs() -> List[Run]:
    conn = _get_conn()
    try:
        rows = _rows(conn, "SELECT * FROM runs WHERE status='queued' ORDER BY started_at ASC")
        return [_to_model(Run, r) for r in rows]
    finally:
        conn.close()


def get_last_run_for_monitor(monitor_id: str) -> Optional[Run]:
    conn = _get_conn()
    try:
        row = _one(conn,
            "SELECT * FROM runs WHERE monitor_id=? AND status NOT IN ('queued','running') "
            "ORDER BY started_at DESC LIMIT 1", (monitor_id,))
        return _to_model(Run, row) if row else None
    finally:
        conn.close()


# ── Runs ───────────────────────────────────────────────────────────────────────

def create_run(run: Run) -> None:
    conn = _get_conn()
    try:
        _exec(conn,
            "INSERT INTO runs (id,monitor_id,project_id,status,started_at,quality_status) "
            "VALUES (?,?,?,?,?,?)",
            (run.id, run.monitor_id, run.project_id, run.status,
             run.started_at or _now(), run.quality_status or "ok"))
        _commit(conn)
    finally:
        conn.close()


def update_run(run: Run) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            UPDATE runs SET
                status=?,finished_at=?,total_posts=?,total_comments=?,
                quality_status=?,warning_message=?,error_message=?,
                export_path=?,handoff_json_path=?,top_keywords_json=?
            WHERE id=?
        """, (run.status, run.finished_at, run.total_posts, run.total_comments,
              run.quality_status, run.warning_message, run.error_message,
              run.export_path, run.handoff_json_path, run.top_keywords_json, run.id))
        _commit(conn)
    finally:
        conn.close()


def get_run(run_id: str) -> Optional[Run]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM runs WHERE id=?", (run_id,))
        return _to_model(Run, row) if row else None
    finally:
        conn.close()


def list_runs(limit: int = 20, monitor_id: str = None, project_id: str = None) -> List[Run]:
    conn = _get_conn()
    try:
        conditions, params = [], []
        if monitor_id:
            conditions.append("monitor_id=?"); params.append(monitor_id)
        if project_id:
            conditions.append("project_id=?"); params.append(project_id)
        q = "SELECT * FROM runs"
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = _rows(conn, q, tuple(params))
        return [_to_model(Run, r) for r in rows]
    finally:
        conn.close()


# ── Exports ────────────────────────────────────────────────────────────────────

def create_export(export: Export) -> None:
    conn = _get_conn()
    try:
        _exec(conn,
            "INSERT INTO exports (id,run_id,format,file_path,drive_file_id,"
            "drive_web_view_link,drive_download_link,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (export.id, export.run_id, export.format, export.file_path,
             export.drive_file_id, export.drive_web_view_link,
             export.drive_download_link, export.created_at or _now()))
        _commit(conn)
    finally:
        conn.close()


def update_export_drive(export_id: str, drive_file_id: str,
                        drive_web_view_link: str, drive_download_link: str) -> None:
    conn = _get_conn()
    try:
        _exec(conn,
            "UPDATE exports SET drive_file_id=?,drive_web_view_link=?,drive_download_link=? WHERE id=?",
            (drive_file_id, drive_web_view_link, drive_download_link, export_id))
        _commit(conn)
    finally:
        conn.close()


def list_exports_for_run(run_id: str) -> List[Export]:
    conn = _get_conn()
    try:
        rows = _rows(conn, "SELECT * FROM exports WHERE run_id=? ORDER BY created_at", (run_id,))
        return [_to_model(Export, r) for r in rows]
    finally:
        conn.close()


# ── SubredditPresets ───────────────────────────────────────────────────────────

def upsert_subreddit_preset(p: SubredditPreset) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO subreddit_presets
                (id,owner_telegram_id,project_id,name,description,subreddits,is_system,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                subreddits=excluded.subreddits, is_system=excluded.is_system,
                updated_at=excluded.updated_at
        """, (p.id, p.owner_telegram_id, p.project_id, p.name, p.description,
              p.subreddits, int(p.is_system), p.created_at or _now(), _now()))
        _commit(conn)
    finally:
        conn.close()


def get_subreddit_preset(preset_id: str) -> Optional[SubredditPreset]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM subreddit_presets WHERE id=?", (preset_id,))
        return _to_model(SubredditPreset, row) if row else None
    finally:
        conn.close()


def list_subreddit_presets(
    owner_telegram_id: int = None,
    include_system: bool = True,
) -> List[SubredditPreset]:
    conn = _get_conn()
    try:
        conditions, params = [], []
        if include_system:
            if owner_telegram_id is not None:
                conditions.append("(is_system=1 OR owner_telegram_id=?)")
                params.append(owner_telegram_id)
        else:
            if owner_telegram_id is not None:
                conditions.append("owner_telegram_id=? AND is_system=0")
                params.append(owner_telegram_id)
        q = "SELECT * FROM subreddit_presets"
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY is_system DESC, name"
        rows = _rows(conn, q, tuple(params))
        return [_to_model(SubredditPreset, r) for r in rows]
    finally:
        conn.close()


# ── KeywordPresets ─────────────────────────────────────────────────────────────

def upsert_keyword_preset(p: KeywordPreset) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO keyword_presets
                (id,owner_telegram_id,project_id,name,description,keywords,language,is_system,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                keywords=excluded.keywords, language=excluded.language,
                is_system=excluded.is_system, updated_at=excluded.updated_at
        """, (p.id, p.owner_telegram_id, p.project_id, p.name, p.description,
              p.keywords, p.language, int(p.is_system), p.created_at or _now(), _now()))
        _commit(conn)
    finally:
        conn.close()


def get_keyword_preset(preset_id: str) -> Optional[KeywordPreset]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM keyword_presets WHERE id=?", (preset_id,))
        return _to_model(KeywordPreset, row) if row else None
    finally:
        conn.close()


def list_keyword_presets(
    owner_telegram_id: int = None,
    include_system: bool = True,
) -> List[KeywordPreset]:
    conn = _get_conn()
    try:
        conditions, params = [], []
        if include_system:
            if owner_telegram_id is not None:
                conditions.append("(is_system=1 OR owner_telegram_id=?)")
                params.append(owner_telegram_id)
        else:
            if owner_telegram_id is not None:
                conditions.append("owner_telegram_id=? AND is_system=0")
                params.append(owner_telegram_id)
        q = "SELECT * FROM keyword_presets"
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY is_system DESC, name"
        rows = _rows(conn, q, tuple(params))
        return [_to_model(KeywordPreset, r) for r in rows]
    finally:
        conn.close()
