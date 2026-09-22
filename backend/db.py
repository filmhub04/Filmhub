import sqlite3
import os
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "films.db"
_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db():
    conn = _get_conn()
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gid TEXT,
            title TEXT,
            link TEXT,
            poster TEXT,
            status TEXT,
            progress REAL,
            size TEXT,
            speed TEXT,
            eta TEXT,
            error TEXT,
            created_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            poster TEXT,
            note TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            poster TEXT,
            position REAL,
            duration REAL,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    ensure_column("downloads", "speed", "TEXT")
    ensure_column("downloads", "eta", "TEXT")
    ensure_column("downloads", "genres", "TEXT DEFAULT ''")
    conn.commit()


def ensure_column(table, column, ddl):
    try:
        conn = _get_conn()
        cols = [r[0] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()
    except Exception:
        pass


def query(sql, params=()):
    try:
        conn = _get_conn()
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def execute(sql, params=()):
    try:
        conn = _get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    except Exception:
        return None


def executemany(sql, params_list):
    try:
        conn = _get_conn()
        conn.executemany(sql, params_list)
        conn.commit()
    except Exception:
        pass
