"""Tests for db/migrations.py — migration system."""

from __future__ import annotations

import sqlite3

import pytest

from app.db.migrations import (
    MIGRATIONS,
    _apply_migration,
    _get_schema_version,
    run_migrations,
)


class TestSchemaVersion:
    """Tests for schema version tracking."""

    def test_get_schema_version_returns_zero_when_no_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            assert _get_schema_version(conn) == 0
        finally:
            conn.close()

    def test_get_schema_version_returns_max_version(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
            conn.execute("INSERT INTO schema_version VALUES (1, '2024-01-01T00:00:00Z')")
            conn.execute("INSERT INTO schema_version VALUES (2, '2024-01-02T00:00:00Z')")
            conn.commit()
            assert _get_schema_version(conn) == 2
        finally:
            conn.close()


class TestApplyMigration:
    """Tests for applying individual migrations."""

    def test_apply_creates_tables_and_records_version(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            migration_sql = MIGRATIONS[0][1]
            _apply_migration(conn, 1, migration_sql)

            # Check schema_version was updated
            assert _get_schema_version(conn) == 1

            # Check all tables exist
            for table in (
                "schema_version",
                "users_profile",
                "watchlist",
                "positions",
                "trades",
                "portfolio_snapshots",
                "chat_messages",
            ):
                result = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                assert result is not None, f"Table {table} not created"
        finally:
            conn.close()

    def test_apply_migration_is_idempotent(self, tmp_path):
        """Tables use IF NOT EXISTS so re-applying the same migration SQL is safe."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            migration_sql = MIGRATIONS[0][1]
            _apply_migration(conn, 1, migration_sql)
            # Re-running the SQL on an already-migrated DB is a no-op for tables
            _apply_migration(conn, 2, migration_sql)
            assert _get_schema_version(conn) == 2
        finally:
            conn.close()


class TestRunMigrations:
    """Integration tests for the full migration runner."""

    def test_run_migrations_applies_all_pending(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("DB_PATH", db_path)

        version = run_migrations(db_path)
        assert version == MIGRATIONS[-1][0]

    def test_run_migrations_idempotent(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("DB_PATH", db_path)

        run_migrations(db_path)
        run_migrations(db_path)  # second call should be no-op
        run_migrations(db_path)  # third call also fine

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            assert _get_schema_version(conn) == MIGRATIONS[-1][0]
            # No duplicate version rows
            count = conn.execute(
                "SELECT COUNT(*) FROM schema_version"
            ).fetchone()[0]
            assert count == len(MIGRATIONS)
        finally:
            conn.close()

    def test_all_required_tables_created(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("DB_PATH", db_path)

        run_migrations(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            expected = {
                "schema_version",
                "users_profile",
                "watchlist",
                "positions",
                "trades",
                "portfolio_snapshots",
                "chat_messages",
            }
            assert tables == expected, f"Missing tables: {expected - tables}"
        finally:
            conn.close()

    def test_constraints_enforced(self, tmp_db):
        """UNIQUE and CHECK constraints are enforced by SQLite."""
        import sqlite3

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        try:
            # UNIQUE constraint on watchlist(user_id, ticker)
            from app.db import add_to_watchlist

            result1 = add_to_watchlist("DUPE1")
            assert result1["added"] is True
            result2 = add_to_watchlist("DUPE1")
            assert result2["added"] is False

            # CHECK constraint on trades.side — invalid side raises IntegrityError
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "trade-1",
                        "default",
                        "AAPL",
                        "hold",  # invalid side — violates CHECK(side IN ('buy', 'sell'))
                        1.0,
                        100.0,
                        "2024-01-01T00:00:00Z",
                    ),
                )
        finally:
            conn.close()
