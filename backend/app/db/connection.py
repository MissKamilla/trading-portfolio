"""SQLite connection management."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Outside Docker (where /app doesn't exist), use a local path relative to this file.
_DEFAULT_DB = "/app/db/finally.db"
if not os.path.exists("/app"):
    _DEFAULT_DB = str(Path(__file__).parent.parent.parent / "db" / "finally.db")
DB_PATH = os.environ.get("DB_PATH", _DEFAULT_DB)


@contextmanager
def get_connection(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager that yields a SQLite connection.

    Creates the parent directory if it does not exist so that the database
    file can be created on first use.
    """
    db_path = path or DB_PATH
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Return a bare SQLite connection (caller manages commit/close)."""
    db_path = os.environ.get("DB_PATH", DB_PATH)
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
