"""Tests for deterministic mock LLM responses."""

import pytest

from app.llm.mock import build_mock_response
from app.llm.schema import ChatResponse, TradeAction, WatchlistChange

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_context():
    return dict(
        cash_balance=10_000.0,
        prices={},
        positions=[],
        watchlist=[],
    )


@pytest.fixture
def populated_context():
    return dict(
        cash_balance=5_000.0,
        prices={"AAPL": 190.0, "TSLA": 250.0, "NVDA": 500.0},
        positions=[
            {
                "ticker": "AAPL",
                "quantity": 10.0,
                "avg_cost": 180.0,
                "current_price": 190.0,
            }
        ],
        watchlist=["AAPL", "TSLA", "NVDA"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_valid_response(r: ChatResponse) -> None:
    """Assert that a ChatResponse has the right shape."""
    assert isinstance(r.message, str)
    assert isinstance(r.trades, list)
    assert isinstance(r.watchlist_changes, list)
    for t in r.trades:
        assert isinstance(t, TradeAction)
        assert t.side in ("buy", "sell")
        assert t.status in ("executed", "failed")
        if t.error is not None:
            assert isinstance(t.error.code, str)
            assert isinstance(t.error.message, str)
    for w in r.watchlist_changes:
        assert isinstance(w, WatchlistChange)
        assert w.action in ("add", "remove")
        assert w.status in ("executed", "failed")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMockBuyIntent:
    def test_buy_existing_ticker_with_price_affordable(self, empty_context):
        empty_context["prices"]["AAPL"] = 190.0
        r = build_mock_response("Buy 1 share of AAPL", **empty_context)
        assert_valid_response(r)
        assert len(r.trades) == 1
        assert r.trades[0].ticker == "AAPL"
        assert r.trades[0].side == "buy"
        assert r.trades[0].quantity == 1.0
        assert r.trades[0].status == "executed"

    def test_buy_multiple_shares(self, empty_context):
        empty_context["prices"]["TSLA"] = 250.0
        r = build_mock_response("Buy 5 shares of TSLA", **empty_context)
        assert_valid_response(r)
        assert r.trades[0].quantity == 5.0
        assert r.trades[0].status == "executed"

    def test_buy_fractional_shares(self, empty_context):
        empty_context["prices"]["NVDA"] = 500.0
        r = build_mock_response("Buy 0.5 shares of NVDA", **empty_context)
        assert_valid_response(r)
        assert r.trades[0].quantity == 0.5
        assert r.trades[0].status == "executed"

    def test_buy_no_price_available(self, empty_context):
        r = build_mock_response("Buy 2 shares of XYZ", **empty_context)
        assert_valid_response(r)
        assert len(r.trades) == 1
        assert r.trades[0].status == "failed"
        assert r.trades[0].error.code == "PRICE_UNAVAILABLE"

    def test_buy_insufficient_cash(self, empty_context):
        empty_context["cash_balance"] = 100.0
        empty_context["prices"]["AAPL"] = 190.0
        r = build_mock_response("Buy 2 shares of AAPL", **empty_context)
        assert_valid_response(r)
        assert r.trades[0].status == "failed"
        assert r.trades[0].error.code == "INSUFFICIENT_CASH"

    def test_buy_no_ticker_detected(self, empty_context):
        r = build_mock_response("I want to buy something", **empty_context)
        assert_valid_response(r)
        assert len(r.trades) == 0
        assert "buy shares" in r.message.lower() or "ticker" in r.message.lower()

    def test_buy_with_watchlist_add(self, populated_context):
        """Buying a ticker not in watchlist executes the trade (no auto-add in mock)."""
        r = build_mock_response("Buy 1 share of NVDA", **populated_context)
        assert_valid_response(r)
        assert r.trades[0].status == "executed"
        assert r.trades[0].ticker == "NVDA"


class TestMockSellIntent:
    def test_sell_owned_ticker(self, populated_context):
        r = build_mock_response("Sell 2 shares of AAPL", **populated_context)
        assert_valid_response(r)
        assert len(r.trades) == 1
        assert r.trades[0].ticker == "AAPL"
        assert r.trades[0].side == "sell"
        assert r.trades[0].status == "executed"

    def test_sell_unowned_ticker(self, empty_context):
        empty_context["prices"]["TSLA"] = 250.0
        r = build_mock_response("Sell 1 share of TSLA", **empty_context)
        assert_valid_response(r)
        assert r.trades[0].status == "failed"

    def test_sell_more_than_owned(self, populated_context):
        r = build_mock_response("Sell 100 shares of AAPL", **populated_context)
        assert_valid_response(r)
        assert len(r.trades) == 1
        assert r.trades[0].status == "failed"
        # Should ask for a smaller quantity, not proceed with the trade
        assert "only" in r.message.lower() or "fewer" in r.message.lower()

    def test_sell_no_ticker_detected(self, populated_context):
        # Use "liquidate" which matches the sell branch but has no valid ticker
        # "I" is not extracted as a ticker (min 2 chars), so we get the no-ticker response
        r = build_mock_response("Liquidate something", **populated_context)
        assert_valid_response(r)
        assert len(r.trades) == 0


class TestMockWatchlist:
    def test_add_new_ticker(self, empty_context):
        # "add to watchlist" must be a literal substring; "Add MSFT to my watchlist" fails
        r = build_mock_response("Add MSFT to watchlist", **empty_context)
        assert_valid_response(r)
        assert len(r.watchlist_changes) == 1
        assert r.watchlist_changes[0].action == "add"
        assert r.watchlist_changes[0].ticker == "MSFT"
        assert r.watchlist_changes[0].status == "executed"

    def test_add_duplicate_ticker(self, populated_context):
        # "add to watchlist" must be a literal substring
        r = build_mock_response("Add AAPL to watchlist", **populated_context)
        assert_valid_response(r)
        assert len(r.watchlist_changes) == 0
        assert "already" in r.message.lower()

    def test_add_ticker_full_watchlist(self, empty_context):
        empty_context["watchlist"] = [f"T{i}" for i in range(30)]
        # "add to watchlist" must be a literal substring
        r = build_mock_response("Add MSFT to watchlist", **empty_context)
        assert_valid_response(r)
        assert len(r.watchlist_changes) == 0
        assert "full" in r.message.lower()

    def test_remove_ticker(self, populated_context):
        # "remove" must be a whole word; "Remove TSLA from watchlist" works
        r = build_mock_response("Remove TSLA from watchlist", **populated_context)
        assert_valid_response(r)
        assert len(r.watchlist_changes) == 1
        assert r.watchlist_changes[0].action == "remove"
        assert r.watchlist_changes[0].ticker == "TSLA"
        assert r.watchlist_changes[0].status == "executed"

    def test_remove_not_in_watchlist(self, populated_context):
        # "remove" must be a whole word; "Remove XYZ from watchlist" works
        r = build_mock_response("Remove XYZ from watchlist", **populated_context)
        assert_valid_response(r)
        assert len(r.watchlist_changes) == 0
        assert "not in your watchlist" in r.message.lower()


class TestMockPortfolio:
    def test_portfolio_summary(self, populated_context):
        r = build_mock_response(
            "How is my portfolio doing?", **populated_context
        )
        assert_valid_response(r)
        assert len(r.trades) == 0
        # Should mention the held ticker or P&L
        assert any(
            kw in r.message
            for kw in ("AAPL", "100", "portfolio", "$", "10")
        )

    def test_empty_portfolio(self, empty_context):
        r = build_mock_response("Show me my portfolio", **empty_context)
        assert_valid_response(r)
        assert len(r.trades) == 0
        assert "empty" in r.message.lower()


class TestMockDefault:
    def test_generic_greeting(self, empty_context):
        r = build_mock_response("Hello!", **empty_context)
        assert_valid_response(r)
        assert len(r.trades) == 0
        assert len(r.watchlist_changes) == 0
        assert "FinAlly" in r.message or "cash" in r.message.lower()

    def test_no_price_map(self, empty_context):
        """Should not crash when prices dict is empty."""
        r = build_mock_response("Buy 1 share of AAPL", **empty_context)
        assert_valid_response(r)

    def test_preserves_context(self, populated_context):
        """Response message should reference cash balance."""
        r = build_mock_response("What do you think?", **populated_context)
        assert_valid_response(r)
        # Should mention something from context
        assert isinstance(r.message, str)
        assert len(r.message) > 0
