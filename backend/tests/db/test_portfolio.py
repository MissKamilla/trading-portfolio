"""Tests for db/__init__.py — watchlist and general DB functions."""

from __future__ import annotations

from app.db import (
    DEFAULT_USER_ID,
    add_message,
    add_to_watchlist,
    get_messages,
    get_or_create_user,
    get_snapshots,
    get_trade_history,
    get_watchlist,
    record_snapshot,
    record_trade,
    remove_from_watchlist,
)


class TestUserProfile:
    """Tests for user profile functions."""

    def test_get_or_create_user_creates_default_user(self, tmp_db):
        user = get_or_create_user()
        assert user["id"] == DEFAULT_USER_ID
        assert user["cash_balance"] == 10_000.0

    def test_get_or_create_user_idempotent(self, tmp_db):
        u1 = get_or_create_user()
        u2 = get_or_create_user()
        assert u1["id"] == u2["id"] == DEFAULT_USER_ID

    def test_cash_balance_default(self, tmp_db):
        from app.db import get_cash_balance

        assert get_cash_balance() == 10_000.0


class TestWatchlist:
    """Tests for watchlist CRUD operations."""

    def test_get_watchlist_initially_has_10_tickers(self, tmp_db):
        items = get_watchlist()
        tickers = {item["ticker"] for item in items}
        assert len(tickers) == 10
        assert tickers == {
            "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
            "NVDA", "META", "JPM", "V", "NFLX",
        }

    def test_add_to_watchlist_normalises_ticker(self, tmp_db):
        # "xyz" is not in the seeded watchlist so we can add it and verify normalisation
        result = add_to_watchlist("xyz")
        assert result["ticker"] == "XYZ"
        assert result["added"] is True

        items = get_watchlist()
        assert "XYZ" in {item["ticker"] for item in items}

    def test_add_to_watchlist_rejects_duplicate(self, tmp_db):
        add_to_watchlist("MSFT")
        result = add_to_watchlist("msft")
        assert result["added"] is False
        assert result["error"] == "ALREADY_EXISTS"

    def test_add_to_watchlist_respects_30_limit(self, tmp_db):
        # Remove all existing first
        for item in get_watchlist():
            remove_from_watchlist(item["ticker"])

        for i in range(30):
            result = add_to_watchlist(f"T{i}")
            assert result["added"] is True, f"Failed to add T{i}"

        # 31st should fail
        result = add_to_watchlist("OVERLIMIT")
        assert result["added"] is False
        assert result["error"] == "WATCHLIST_FULL"

    def test_remove_from_watchlist(self, tmp_db):
        remove_from_watchlist("AAPL")
        items = get_watchlist()
        assert "AAPL" not in {item["ticker"] for item in items}

    def test_remove_nonexistent_returns_removed_false(self, tmp_db):
        result = remove_from_watchlist("ZZZZ")
        assert result["removed"] is False

    def test_watchlist_order_preserved(self, tmp_db):
        remove_from_watchlist("AAPL")
        add_to_watchlist("AAPL")
        items = get_watchlist()
        tickers = [item["ticker"] for item in items]
        assert tickers[-1] == "AAPL"


class TestTrades:
    """Tests for trade recording."""

    def test_record_trade_returns_expected_fields(self, tmp_db):
        trade = record_trade(
            user_id=DEFAULT_USER_ID,
            ticker="AAPL",
            side="buy",
            quantity=5.0,
            price=190.0,
        )
        assert trade["ticker"] == "AAPL"
        assert trade["side"] == "buy"
        assert trade["quantity"] == 5.0
        assert trade["price"] == 190.0
        assert "id" in trade
        assert "executed_at" in trade

    def test_get_trade_history_returns_most_recent_first(self, tmp_db):
        record_trade(DEFAULT_USER_ID, "AAPL", "buy", 1.0, 100.0)
        record_trade(DEFAULT_USER_ID, "GOOGL", "buy", 1.0, 100.0)
        history = get_trade_history()
        assert len(history) >= 2
        # Most recent first
        assert history[0]["ticker"] == "GOOGL"
        assert history[1]["ticker"] == "AAPL"


class TestSnapshots:
    """Tests for portfolio snapshots."""

    def test_record_snapshot(self, tmp_db):
        snap = record_snapshot(DEFAULT_USER_ID, 10_000.0)
        assert snap["total_value"] == 10_000.0
        assert "id" in snap
        assert "recorded_at" in snap

    def test_get_snapshots_oldest_first(self, tmp_db):
        record_snapshot(DEFAULT_USER_ID, 10_000.0)
        record_snapshot(DEFAULT_USER_ID, 11_000.0)
        snaps = get_snapshots()
        values = [s["total_value"] for s in snaps]
        assert values == sorted(values)


class TestChatMessages:
    """Tests for chat message storage."""

    def test_add_message_user_role(self, tmp_db):
        msg = add_message(DEFAULT_USER_ID, "user", "Buy AAPL")
        assert msg["role"] == "user"
        assert msg["content"] == "Buy AAPL"
        assert msg["actions"] is None
        assert "id" in msg

    def test_add_message_assistant_role_with_actions(self, tmp_db):
        import json

        actions = json.dumps([{"action": "buy", "ticker": "AAPL"}])
        msg = add_message(DEFAULT_USER_ID, "assistant", "Done!", actions)
        assert msg["role"] == "assistant"
        assert msg["actions"] == actions

    def test_get_messages_returns_oldest_first(self, tmp_db):
        add_message(DEFAULT_USER_ID, "user", "First")
        add_message(DEFAULT_USER_ID, "assistant", "Second")
        add_message(DEFAULT_USER_ID, "user", "Third")
        msgs = get_messages()
        contents = [m["content"] for m in msgs]
        assert contents == ["First", "Second", "Third"]

    def test_get_messages_respects_limit(self, tmp_db):
        for i in range(5):
            add_message(DEFAULT_USER_ID, "user", f"Msg {i}")
        msgs = get_messages(limit=3)
        assert len(msgs) == 3
