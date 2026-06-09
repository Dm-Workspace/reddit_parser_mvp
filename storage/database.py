"""
Dual-backend storage layer: Postgres (via DATABASE_URL) or SQLite fallback.

Postgres:  set DATABASE_URL=postgresql://user:pass@host:port/dbname
SQLite:    falls back to data/tracker.db when DATABASE_URL is not set

All public functions return dataclass instances from storage.models.
SQL uses ? placeholders internally — auto-replaced with %s for Postgres.
"""
import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
from storage.models import Project, Monitor, Run, Export

# ── Backend detection ──────────────────────────────────────────────────────────
_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_PG = _DATABASE_URL.startswith(("postgres://", "postgresql://"))
_PH = "%s" if _USE_PG else "?"           # SQL placeholder character
_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tracker.db")


# ── Connection helpers ─────────────────────────────────────────────────────────

def _get_conn():
    if _USE_PG:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        return conn
    else:
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
    else:
        return conn.execute(sql, params)


def _rows(conn, sql: str, params: tuple = ()) -> List[dict]:
    cur = _exec(conn, sql, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def _one(conn, sql: str, params: tuple = ()) -> Optional[dict]:
    results = _rows(conn, sql, params)
    return results[0] if results else None


def _commit(conn):
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Schema ─────────────────────────────────────────────────────────────────────

_CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    description             TEXT DEFAULT '',
    language                TEXT DEFAULT 'en',
    market                  TEXT DEFAULT '',
    default_output_language TEXT DEFAULT 'en',
    enabled                 INTEGER DEFAULT 1,
    created_at              TEXT
);

CREATE TABLE IF NOT EXISTS monitors (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    name             TEXT NOT NULL,
    source           TEXT DEFAULT 'reddit',
    subreddit_preset TEXT NOT NULL,
    keyword_preset   TEXT NOT NULL,
    run_mode         TEXT NOT NULL,
    schedule_cron    TEXT DEFAULT '',
    timezone         TEXT DEFAULT 'UTC',
    enabled          INTEGER DEFAULT 1,
    export_formats   TEXT DEFAULT '["xlsx","json"]',
    created_at       TEXT,
    updated_at       TEXT
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
    file_path           TEXT NOT NULL DEFAULT '',
    drive_file_id       TEXT,
    drive_web_view_link TEXT,
    drive_download_link TEXT,
    created_at          TEXT
);
"""

_MIGRATIONS_SQLITE = [
    # table, column, definition
    ("runs",    "quality_status",    "TEXT DEFAULT 'ok'"),
    ("runs",    "warning_message",   "TEXT"),
    ("runs",    "top_keywords_json", "TEXT"),
    ("exports", "drive_file_id",     "TEXT"),
    ("exports", "drive_web_view_link","TEXT"),
    ("exports", "drive_download_link","TEXT"),
]

_MIGRATIONS_PG = [
    "ALTER TABLE runs    ADD COLUMN IF NOT EXISTS quality_status    TEXT DEFAULT 'ok'",
    "ALTER TABLE runs    ADD COLUMN IF NOT EXISTS warning_message   TEXT",
    "ALTER TABLE runs    ADD COLUMN IF NOT EXISTS top_keywords_json TEXT",
    "ALTER TABLE exports ADD COLUMN IF NOT EXISTS drive_file_id     TEXT",
    "ALTER TABLE exports ADD COLUMN IF NOT EXISTS drive_web_view_link TEXT",
    "ALTER TABLE exports ADD COLUMN IF NOT EXISTS drive_download_link TEXT",
]


def init_db() -> None:
    conn = _get_conn()
    try:
        if _USE_PG:
            cur = conn.cursor()
            # create tables
            for stmt in _CREATE_SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
            # migrations
            for sql in _MIGRATIONS_PG:
                try:
                    cur.execute(sql)
                except Exception:
                    pass   # column might already exist
        else:
            conn.executescript(_CREATE_SCHEMA)
            # sqlite migrations for existing DBs
            for table, col, typedef in _MIGRATIONS_SQLITE:
                existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        _commit(conn)
        logger.debug(f"DB initialised ({'postgres' if _USE_PG else _SQLITE_PATH})")
    finally:
        conn.close()


# ── Projects ───────────────────────────────────────────────────────────────────

def upsert_project(p: Project) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO projects (id,name,description,language,market,default_output_language,enabled,created_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                language=excluded.language, market=excluded.market,
                default_output_language=excluded.default_output_language,
                enabled=excluded.enabled
        """, (p.id, p.name, p.description, p.language, p.market,
              p.default_output_language, int(p.enabled), p.created_at or _now()))
        _commit(conn)
    finally:
        conn.close()


def get_project(project_id: str) -> Optional[Project]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
        if not row:
            return None
        row["enabled"] = bool(row["enabled"])
        return Project(**{k: row[k] for k in Project.__dataclass_fields__ if k in row})
    finally:
        conn.close()


# ── Monitors ───────────────────────────────────────────────────────────────────

def upsert_monitor(m: Monitor) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO monitors
                (id,project_id,name,source,subreddit_preset,keyword_preset,
                 run_mode,schedule_cron,timezone,enabled,export_formats,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                project_id=excluded.project_id, name=excluded.name,
                subreddit_preset=excluded.subreddit_preset,
                keyword_preset=excluded.keyword_preset,
                run_mode=excluded.run_mode, schedule_cron=excluded.schedule_cron,
                timezone=excluded.timezone, enabled=excluded.enabled,
                export_formats=excluded.export_formats, updated_at=excluded.updated_at
        """, (m.id, m.project_id, m.name, m.source, m.subreddit_preset,
              m.keyword_preset, m.run_mode, m.schedule_cron, m.timezone,
              int(m.enabled), m.export_formats, m.created_at or _now(), _now()))
        _commit(conn)
    finally:
        conn.close()


def get_monitor(monitor_id: str) -> Optional[Monitor]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM monitors WHERE id=?", (monitor_id,))
        if not row:
            return None
        row["enabled"] = bool(row["enabled"])
        return Monitor(**{k: row[k] for k in Monitor.__dataclass_fields__ if k in row})
    finally:
        conn.close()


def list_monitors(enabled_only: bool = False) -> List[Monitor]:
    conn = _get_conn()
    try:
        q = "SELECT * FROM monitors"
        if enabled_only:
            q += " WHERE enabled=1"
        q += " ORDER BY project_id, id"
        rows = _rows(conn, q)
        result = []
        for row in rows:
            row["enabled"] = bool(row["enabled"])
            result.append(Monitor(**{k: row[k] for k in Monitor.__dataclass_fields__ if k in row}))
        return result
    finally:
        conn.close()


def get_active_run_for_monitor(monitor_id: str) -> Optional[Run]:
    conn = _get_conn()
    try:
        row = _one(conn,
            "SELECT * FROM runs WHERE monitor_id=? AND status IN ('queued','running') "
            "ORDER BY started_at DESC LIMIT 1",
            (monitor_id,))
        if not row:
            return None
        return Run(**{k: row[k] for k in Run.__dataclass_fields__ if k in row})
    finally:
        conn.close()


def get_queued_runs() -> List[Run]:
    """Return all queued runs ordered by creation time."""
    conn = _get_conn()
    try:
        rows = _rows(conn,
            "SELECT * FROM runs WHERE status='queued' ORDER BY started_at ASC")
        return [Run(**{k: r[k] for k in Run.__dataclass_fields__ if k in r}) for r in rows]
    finally:
        conn.close()


# ── Runs ───────────────────────────────────────────────────────────────────────

def create_run(run: Run) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO runs (id,monitor_id,project_id,status,started_at,quality_status)
            VALUES (?,?,?,?,?,?)
        """, (run.id, run.monitor_id, run.project_id, run.status,
              run.started_at or _now(), run.quality_status or "ok"))
        _commit(conn)
    finally:
        conn.close()


def update_run(run: Run) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            UPDATE runs SET
                status=?, finished_at=?, total_posts=?, total_comments=?,
                quality_status=?, warning_message=?, error_message=?,
                export_path=?, handoff_json_path=?, top_keywords_json=?
            WHERE id=?
        """, (run.status, run.finished_at, run.total_posts, run.total_comments,
              run.quality_status, run.warning_message, run.error_message,
              run.export_path, run.handoff_json_path, run.top_keywords_json,
              run.id))
        _commit(conn)
    finally:
        conn.close()


def get_run(run_id: str) -> Optional[Run]:
    conn = _get_conn()
    try:
        row = _one(conn, "SELECT * FROM runs WHERE id=?", (run_id,))
        if not row:
            return None
        return Run(**{k: row[k] for k in Run.__dataclass_fields__ if k in row})
    finally:
        conn.close()


def list_runs(limit: int = 20, monitor_id: str = None) -> List[Run]:
    conn = _get_conn()
    try:
        if monitor_id:
            rows = _rows(conn,
                "SELECT * FROM runs WHERE monitor_id=? ORDER BY started_at DESC LIMIT ?",
                (monitor_id, limit))
        else:
            rows = _rows(conn,
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [Run(**{k: r[k] for k in Run.__dataclass_fields__ if k in r}) for r in rows]
    finally:
        conn.close()


def get_last_run_for_monitor(monitor_id: str) -> Optional[Run]:
    """Get the most recent completed/failed run (for schedule checks)."""
    conn = _get_conn()
    try:
        row = _one(conn,
            "SELECT * FROM runs WHERE monitor_id=? AND status NOT IN ('queued','running') "
            "ORDER BY started_at DESC LIMIT 1",
            (monitor_id,))
        if not row:
            return None
        return Run(**{k: row[k] for k in Run.__dataclass_fields__ if k in row})
    finally:
        conn.close()


# ── Exports ────────────────────────────────────────────────────────────────────

def create_export(export: Export) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            INSERT INTO exports (id,run_id,format,file_path,drive_file_id,
                                 drive_web_view_link,drive_download_link,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (export.id, export.run_id, export.format, export.file_path,
              export.drive_file_id, export.drive_web_view_link,
              export.drive_download_link, export.created_at or _now()))
        _commit(conn)
    finally:
        conn.close()


def update_export_drive(export_id: str, drive_file_id: str,
                        drive_web_view_link: str, drive_download_link: str) -> None:
    conn = _get_conn()
    try:
        _exec(conn, """
            UPDATE exports SET
                drive_file_id=?, drive_web_view_link=?, drive_download_link=?
            WHERE id=?
        """, (drive_file_id, drive_web_view_link, drive_download_link, export_id))
        _commit(conn)
    finally:
        conn.close()


def list_exports_for_run(run_id: str) -> List[Export]:
    conn = _get_conn()
    try:
        rows = _rows(conn,
            "SELECT * FROM exports WHERE run_id=? ORDER BY created_at", (run_id,))
        return [Export(**{k: r[k] for k in Export.__dataclass_fields__ if k in r}) for r in rows]
    finally:
        conn.close()
