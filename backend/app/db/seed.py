"""Seed data for a fresh database."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

DEFAULT_USER_ID = "default"
DEFAULT_CASH_BALANCE = 10_000.0

DEFAULT_TICKERS = [
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
]


def seed_database(conn: sqlite3.Connection) -> None:
    """Seed a freshly-initialised database with default data.

    This function is idempotent: it checks whether the watchlist already
    contains entries before inserting anything.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Ensure the default user exists
    conn.execute(
        """
        INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at)
        VALUES (?, ?, ?)
        """,
        (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
    )

    # Seed watchlist only when it is empty (avoids duplicate rows on re-init)
    count = conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = ?",
        (DEFAULT_USER_ID,),
    ).fetchone()[0]

    if count == 0:
        rows = [
            (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, now)
            for ticker in DEFAULT_TICKERS
        ]
        conn.executemany(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            rows,
        )

    conn.commit()
