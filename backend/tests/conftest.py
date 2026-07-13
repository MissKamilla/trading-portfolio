"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Create a temporary database for a single test.

    Resets the module-level init flag first so that each test gets a fresh
    database backed by a temp file (isolated via DB_PATH env var).
    """
    import app.db as db_module
    import app.db.connection as conn_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setattr(conn_module, "DB_PATH", db_path)

    # Reset before init so the temp DB is used, not the default path
    db_module._db_initialised = False
    db_module.init_db(db_path)

    yield db_path

    # Reset after so the next test also starts clean
    db_module._db_initialised = False
