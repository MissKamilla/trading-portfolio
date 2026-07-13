"""Database migration system.

Migrations are applied lazily on first database access. Each migration is
identified by an integer version number. The `schema_version` table tracks
which versions have been applied.

Adding a new migration:
    1. Append it to the MIGRATIONS list below.
    2. Increment the final version number in the list.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

# All migrations must be listed here in order.
MIGRATIONS: list[tuple[int, str]] = [
    # Version 1: create all initial tables
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version  INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users_profile (
            id          TEXT PRIMARY KEY DEFAULT 'default',
            cash_balance REAL NOT NULL DEFAULT 10000.0,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id        TEXT PRIMARY KEY,
            user_id   TEXT NOT NULL DEFAULT 'default',
            ticker    TEXT NOT NULL,
            added_at  TEXT NOT NULL,
            UNIQUE(user_id, ticker)
        );

        CREATE TABLE IF NOT EXISTS positions (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL DEFAULT 'default',
            ticker     TEXT NOT NULL,
            quantity   REAL NOT NULL,
            avg_cost   REAL NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, ticker)
        );

        CREATE TABLE IF NOT EXISTS trades (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL DEFAULT 'default',
            ticker      TEXT NOT NULL,
            side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            quantity    REAL NOT NULL,
            price       REAL NOT NULL,
            executed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL DEFAULT 'default',
            total_value  REAL NOT NULL,
            recorded_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL DEFAULT 'default',
            role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content    TEXT NOT NULL,
            actions    TEXT,
            created_at TEXT NOT NULL
        );
        """,
    ),
]


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version (0 if not yet initialised)."""
    try:
        row = conn.execute(
            "SELECT MAX(version) AS v FROM schema_version"
        ).fetchone()
        return row["v"] if row and row["v"] is not None else 0
    except Exception:
        return 0


def _apply_migration(
    conn: sqlite3.Connection, version: int, sql: str
) -> None:
    """Apply a single migration inside an explicit transaction."""
    now = datetime.now(timezone.utc).isoformat()
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
        (version, now),
    )
    conn.commit()


def run_migrations(path: str | None = None) -> int:
    """Run any un-applied migrations and return the new schema version.

    This function is idempotent — running it on a fully-migrated database
    is a no-op.
    """
    from .connection import get_connection

    with get_connection(path) as conn:
        current = _get_schema_version(conn)

        pending = [
            (v, sql) for v, sql in MIGRATIONS if v > current
        ]

        for version, sql in pending:
            _apply_migration(conn, version, sql)

        return _get_schema_version(conn)
