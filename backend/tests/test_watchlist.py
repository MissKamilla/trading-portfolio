"""Tests for watchlist DB operations and API."""

from __future__ import annotations

from app.db import add_to_watchlist, get_watchlist, remove_from_watchlist


class TestWatchlistAdd:
    """Test adding tickers to the watchlist."""

    def test_add_single_ticker(self, tmp_db: str) -> None:
        """Adding a ticker returns added=True."""
        result = add_to_watchlist("XYZNEW")
        assert result["ticker"] == "XYZNEW"
        assert result["added"] is True
        assert result.get("error") is None

    def test_add_ticker_appears_in_list(self, tmp_db: str) -> None:
        """After adding, ticker must appear in get_watchlist."""
        add_to_watchlist("TSLA")
        watchlist = get_watchlist()
        tickers = [item["ticker"] for item in watchlist]
        assert "TSLA" in tickers

    def test_add_normalizes_to_uppercase(self, tmp_db: str) -> None:
        """Lower/mixed-case ticker must be stored as uppercase."""
        add_to_watchlist("tsla")
        watchlist = get_watchlist()
        tickers = [item["ticker"] for item in watchlist]
        assert "TSLA" in tickers
        assert "tsla" not in tickers

    def test_add_same_ticker_twice_returns_false(self, tmp_db: str) -> None:
        """Adding the same ticker twice must return added=False with ALREADY_EXISTS."""
        add_to_watchlist("NVDA")
        result = add_to_watchlist("NVDA")
        assert result["added"] is False
        assert result.get("error") == "ALREADY_EXISTS"

    def test_add_ticker_has_uuid_id(self, tmp_db: str) -> None:
        """Each watchlist entry must have a UUID id."""
        add_to_watchlist("META")
        items = get_watchlist()
        assert len(items) >= 1
        last = items[-1]
        assert "id" in last
        assert len(last["id"]) == 36  # UUID format

    def test_add_ticker_has_added_at(self, tmp_db: str) -> None:
        """Each watchlist entry must have an added_at ISO timestamp."""
        add_to_watchlist("NFLX")
        items = get_watchlist()
        last = items[-1]
        assert "added_at" in last
        assert "T" in last["added_at"]  # ISO format contains T


class TestWatchlistRemove:
    """Test removing tickers from the watchlist."""

    def test_remove_existing_ticker(self, tmp_db: str) -> None:
        """Removing an existing ticker returns removed=True."""
        add_to_watchlist("AMD")
        result = remove_from_watchlist("AMD")
        assert result["removed"] is True
        assert result.get("error") is None

    def test_remove_ticker_disappears_from_list(self, tmp_db: str) -> None:
        """After removal, ticker must not appear in get_watchlist."""
        add_to_watchlist("AMD")
        remove_from_watchlist("AMD")
        tickers = [item["ticker"] for item in get_watchlist()]
        assert "AMD" not in tickers

    def test_remove_nonexistent_ticker(self, tmp_db: str) -> None:
        """Removing a ticker that doesn't exist must return removed=False."""
        result = remove_from_watchlist("DOES_NOT_EXIST_123")
        assert result["removed"] is False
        assert result.get("error") is None

    def test_remove_normalizes_to_uppercase(self, tmp_db: str) -> None:
        """Removing a lowercase ticker must work (normalised to uppercase)."""
        add_to_watchlist("AMD")
        result = remove_from_watchlist("amd")
        assert result["removed"] is True
        assert result.get("error") is None


class TestWatchlistLimit:
    """Test the 30-ticker watchlist limit."""

    def test_watchlist_limit_reached(self, tmp_db: str) -> None:
        """After 30 tickers, adding a 31st must fail with WATCHLIST_FULL."""
        # The seeded watchlist already has 10 default tickers.
        # Add 20 more to reach the limit of 30.
        for i in range(20):
            add_to_watchlist(f"X{i:02d}")

        # 31st ticker should fail
        result = add_to_watchlist("TOO_BIG")
        assert result["added"] is False
        assert result.get("error") == "WATCHLIST_FULL"

    def test_watchlist_exactly_at_limit(self, tmp_db: str) -> None:
        """Adding tickers up to exactly 30 must succeed."""
        # Add 20 to the 10 seeded tickers = 30 total.
        for i in range(20):
            r = add_to_watchlist(f"TICK{i:02d}")
            assert r["added"] is True

    def test_remove_then_add_below_limit(self, tmp_db: str) -> None:
        """Removing a ticker frees up a slot to add a new one."""
        # Add 20 more to fill the watchlist
        for i in range(20):
            add_to_watchlist(f"FULL{i:02d}")

        # Remove one
        remove_from_watchlist("FULL00")

        # Add a new one (should succeed)
        result = add_to_watchlist("FREED_UP")
        assert result["added"] is True
        assert result.get("error") is None


class TestWatchlistOrdering:
    """Test that watchlist preserves insertion order."""

    def test_watchlist_ordered_by_added_at(self, tmp_db: str) -> None:
        """Items must appear in the order they were added (oldest first)."""
        tickers = ["ZZZZ", "AAAA", "MMMM"]
        for t in tickers:
            add_to_watchlist(t)

        items = get_watchlist()
        # Find our added items (excluding seeded defaults)
        added_items = [item for item in items if item["ticker"] in tickers]
        assert [item["ticker"] for item in added_items] == tickers
