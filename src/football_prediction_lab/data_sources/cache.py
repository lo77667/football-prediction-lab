"""SQLite cache used across data sources to reduce API calls and respect free limits."""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = "data_harvester.db"
TABLE = "data_cache"

def init_cache(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(f"""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS {TABLE} (
        cache_key TEXT PRIMARY KEY,
        source TEXT,
        url TEXT,
        response TEXT,
        fetched_at TEXT
    );
    """)
    conn.commit()
    conn.close()

def get_cache(key: str, max_age_seconds: Optional[int] = None, path: str = DB_PATH) -> Optional[dict]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT response, fetched_at FROM {TABLE} WHERE cache_key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"]) if row["fetched_at"] else None
    if max_age_seconds is not None and fetched_at is not None:
        if datetime.utcnow() - fetched_at > timedelta(seconds=max_age_seconds):
            return None
    return json.loads(row["response"])

def set_cache(key: str, source: str, url: str, response: dict, path: str = DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(f"INSERT OR REPLACE INTO {TABLE} (cache_key, source, url, response, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (key, source, url, json.dumps(response, ensure_ascii=False), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
