"""SQLite connection and table management for idempotency experiments."""
import os
import sqlite3
from pathlib import Path

DB_DIR = Path(os.environ.get("EVENT_LOG", "/lab/data/events.jsonl")).parent
DB_PATH = DB_DIR / "idempotency.db"


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with WAL mode and foreign keys."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(clear: bool = False) -> None:
    """Create tables. If *clear* is True, drop existing data first."""
    conn = get_connection()
    try:
        if clear:
            conn.execute("DELETE FROM business_effects")
            conn.execute("DELETE FROM processed_commands")
            conn.commit()
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS processed_commands (
                    consumer_scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (consumer_scope, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS business_effects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consumer_scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
    finally:
        conn.close()
