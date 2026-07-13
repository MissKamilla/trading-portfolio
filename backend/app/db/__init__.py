"""Public database API for the FinAlly backend.

All functions in this module operate on the database configured via the
``DB_PATH`` environment variable (default: ``/app/db/finally.db``).

All timestamps are stored and returned as ISO-8601 strings in UTC.
User IDs are hardcoded to ``"default"`` for the single-user MVP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .connection import get_connection
from .migrations import run_migrations
from .seed import seed_database

DEFAULT_USER_ID = "default"

# ---------------------------------------------------------------------------
# Module-level initialisation
# ---------------------------------------------------------------------------

_db_initialised = False


def init_db(path: str | None = None) -> None:
    """Run migrations and seed the database.

    This is called lazily by the first function that accesses the DB.
    Calling it explicitly is safe (idempotent).
    """
    global _db_initialised
    if _db_initialised:
        return
    run_migrations(path)
    with get_connection(path) as conn:
        seed_database(conn)
    _db_initialised = True


def _ensure_initialised() -> None:
    """Lazy initialisation guard used by every public function."""
    init_db()


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

def get_or_create_user(
    user_id: str = DEFAULT_USER_ID,
    path: str | None = None,
) -> dict[str, Any]:
    """Return the user profile, creating it with the default balance if absent."""
    _ensure_initialised()
    with get_connection(path) as conn:
        row = conn.execute(
            "SELECT * FROM users_profile WHERE id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                (user_id, 10_000.0, now),
            )
            conn.commit()
            return {"id": user_id, "cash_balance": 10_000.0, "created_at": now}

        return dict(row)


def get_cash_balance(user_id: str = DEFAULT_USER_ID) -> float:
    """Return the user's current cash balance."""
    _ensure_initialised()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return 10_000.0
        return row["cash_balance"]


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def get_watchlist(user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    """Return the user's watchlist ordered by added_at."""
    _ensure_initialised()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, user_id, ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def add_to_watchlist(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Add a ticker to the user's watchlist. Returns the new row.

    Returns an error dict if the ticker is already present or the watchlist
    limit (30) has been reached.
    """
    _ensure_initialised()
    ticker = ticker.upper().strip()

    with get_connection() as conn:
        # Check for duplicate
        existing = conn.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()
        if existing is not None:
            return {"ticker": ticker, "added": False, "error": "ALREADY_EXISTS"}

        # Check limit
        count = conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        if count >= 30:
            return {"ticker": ticker, "added": False, "error": "WATCHLIST_FULL"}

        now = datetime.now(timezone.utc).isoformat()
        row_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (row_id, user_id, ticker, now),
        )
        conn.commit()
        return {"ticker": ticker, "added": True}


def remove_from_watchlist(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Remove a ticker from the user's watchlist."""
    _ensure_initialised()
    ticker = ticker.upper().strip()

    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ? RETURNING id",
            (user_id, ticker),
        )
        deleted = cur.fetchone() is not None
        conn.commit()
        return {"ticker": ticker, "removed": deleted}


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def get_positions(user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
    """Return all open positions for the user."""
    _ensure_initialised()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, user_id, ticker, quantity, avg_cost, updated_at "
            "FROM positions WHERE user_id = ? ORDER BY ticker",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def upsert_position(
    user_id: str,
    ticker: str,
    quantity: float,
    avg_cost: float,
) -> dict[str, Any]:
    """Insert or update a position. Deletes it if quantity <= 0."""
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        if quantity <= 0:
            conn.execute(
                "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            )
        else:
            conn.execute(
                """
                INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, ticker)
                DO UPDATE SET quantity = excluded.quantity,
                              avg_cost   = excluded.avg_cost,
                              updated_at = excluded.updated_at
                """,
                (str(uuid.uuid4()), user_id, ticker, quantity, avg_cost, now),
            )
        conn.commit()

    return {
        "user_id": user_id,
        "ticker": ticker,
        "quantity": quantity,
        "avg_cost": avg_cost,
    }


def delete_position(user_id: str, ticker: str) -> None:
    """Delete a position by user and ticker."""
    ticker = ticker.upper()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def record_trade(
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
) -> dict[str, Any]:
    """Record a trade and return the created trade row."""
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, user_id, ticker, side, quantity, price, now),
        )
        conn.commit()

    return {
        "id": trade_id,
        "user_id": user_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": now,
    }


def get_trade_history(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return recent trades for the user, most recent first."""
    _ensure_initialised()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE user_id = ? ORDER BY executed_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Portfolio snapshots
# ---------------------------------------------------------------------------

def record_snapshot(
    user_id: str,
    total_value: float,
    path: str | None = None,
) -> dict[str, Any]:
    """Record a portfolio value snapshot."""
    now = datetime.now(timezone.utc).isoformat()
    snapshot_id = str(uuid.uuid4())

    with get_connection(path) as conn:
        conn.execute(
            """
            INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (snapshot_id, user_id, total_value, now),
        )
        conn.commit()

    return {"id": snapshot_id, "user_id": user_id, "total_value": total_value, "recorded_at": now}


def get_snapshots(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return portfolio snapshots ordered oldest-first."""
    _ensure_initialised()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_snapshots WHERE user_id = ? ORDER BY recorded_at ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def cleanup_old_snapshots(user_id: str = DEFAULT_USER_ID, days: int = 7) -> int:
    """Delete portfolio snapshots older than `days` days.

    Returns the number of rows deleted.
    """
    _ensure_initialised()
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM portfolio_snapshots WHERE user_id = ? AND recorded_at < ?",
            (user_id, cutoff),
        )
        conn.commit()
        return cur.rowcount


# Alias for backwards compatibility with the background task
create_snapshot = record_snapshot


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

def get_messages(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recent messages for the user, oldest first."""
    _ensure_initialised()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE user_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def add_message(
    user_id: str,
    role: str,
    content: str,
    actions: str | None = None,
) -> dict[str, Any]:
    """Add a message to the conversation history and return the created row."""
    now = datetime.now(timezone.utc).isoformat()
    msg_id = str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, user_id, role, content, actions, now),
        )
        conn.commit()

    return {
        "id": msg_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": now,
    }
