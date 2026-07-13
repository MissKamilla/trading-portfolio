"""Tests for portfolio business logic in db/portfolio.py."""

from __future__ import annotations

from app.db.portfolio import execute_trade, get_portfolio
from app.market.cache import PriceCache


class TestExecuteTrade:
    """Tests for execute_trade validation and side effects."""

    def test_buy_reduces_cash(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        result = execute_trade(
            user_id="default",
            ticker="AAPL",
            side="buy",
            quantity=10.0,
            price=190.0,
            price_cache=cache,
        )

        assert "error" not in result
        assert result["cash_balance"] == 10_000.0 - 10 * 190.0

    def test_sell_increases_cash(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 200.0)

        # First buy
        execute_trade("default", "AAPL", "buy", 10.0, 190.0, cache)
        # Then sell
        result = execute_trade(
            "default", "AAPL", "sell", 5.0, 200.0, cache
        )

        assert "error" not in result
        # Cash: 10k - 1900 + 1000 = 9100
        assert result["cash_balance"] == 9_100.0

    def test_buy_creates_position(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        result = execute_trade(
            "default", "AAPL", "buy", 5.0, 190.0, cache
        )

        pos = result["position"]
        assert pos["ticker"] == "AAPL"
        assert pos["quantity"] == 5.0
        assert pos["avg_cost"] == 190.0

    def test_multiple_buys_compute_weighted_avg_cost(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        execute_trade("default", "AAPL", "buy", 10.0, 100.0, cache)
        result = execute_trade(
            "default", "AAPL", "buy", 10.0, 200.0, cache
        )

        pos = result["position"]
        # avg = (10*100 + 10*200) / 20 = 150
        assert pos["quantity"] == 20.0
        assert pos["avg_cost"] == 150.0

    def test_sell_does_not_change_avg_cost(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        execute_trade("default", "AAPL", "buy", 10.0, 100.0, cache)
        result = execute_trade(
            "default", "AAPL", "sell", 5.0, 200.0, cache
        )

        pos = result["position"]
        assert pos["avg_cost"] == 100.0
        assert pos["quantity"] == 5.0

    def test_sell_all_deletes_position(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        execute_trade("default", "AAPL", "buy", 10.0, 100.0, cache)
        result = execute_trade(
            "default", "AAPL", "sell", 10.0, 100.0, cache
        )

        assert result["position"] is None
        from app.db import get_positions
        positions = get_positions()
        assert all(p["ticker"] != "AAPL" for p in positions)

    def test_buy_fractional_shares(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        result = execute_trade(
            "default", "AAPL", "buy", 1.5, 190.0, cache
        )

        assert result["position"]["quantity"] == 1.5

    def test_buy_insufficient_cash(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        result = execute_trade(
            "default", "AAPL", "buy", 100.0, 190.0, cache
        )

        assert "error" in result
        assert result["error"]["code"] == "INSUFFICIENT_CASH"

    def test_sell_insufficient_shares(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        execute_trade("default", "AAPL", "buy", 5.0, 100.0, cache)
        result = execute_trade(
            "default", "AAPL", "sell", 10.0, 100.0, cache
        )

        assert "error" in result
        assert result["error"]["code"] == "INSUFFICIENT_SHARES"

    def test_sell_without_position(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        result = execute_trade(
            "default", "AAPL", "sell", 5.0, 100.0, cache
        )

        assert "error" in result
        assert result["error"]["code"] == "INSUFFICIENT_SHARES"

    def test_invalid_quantity_zero(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        result = execute_trade(
            "default", "AAPL", "buy", 0.0, 100.0, cache
        )
        assert "error" in result
        assert result["error"]["code"] == "INVALID_QUANTITY"

    def test_invalid_quantity_negative(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        result = execute_trade(
            "default", "AAPL", "buy", -5.0, 100.0, cache
        )
        assert "error" in result
        assert result["error"]["code"] == "INVALID_QUANTITY"

    def test_invalid_side(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 100.0)

        result = execute_trade(
            "default", "AAPL", "hold", 5.0, 100.0, cache
        )
        assert "error" in result
        assert result["error"]["code"] == "INVALID_SIDE"

    def test_ticker_normalised_to_uppercase(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        result = execute_trade(
            "default", "aapl", "buy", 1.0, 190.0, cache
        )
        assert result["trade"]["ticker"] == "AAPL"

    def test_trade_recorded_in_history(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        result = execute_trade(
            "default", "AAPL", "buy", 1.0, 190.0, cache
        )

        from app.db import get_trade_history
        history = get_trade_history()
        trade_ids = [t["id"] for t in history]
        assert result["trade"]["id"] in trade_ids

    def test_snapshot_recorded_after_trade(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        execute_trade("default", "AAPL", "buy", 1.0, 190.0, cache)

        from app.db import get_snapshots
        snaps = get_snapshots()
        assert len(snaps) >= 1


class TestGetPortfolio:
    """Tests for get_portfolio valuation."""

    def test_empty_portfolio_total_equals_cash(self, tmp_db):
        cache = PriceCache()
        portfolio = get_portfolio("default", cache)
        assert portfolio["total_value"] == 10_000.0
        assert portfolio["cash_balance"] == 10_000.0
        assert portfolio["positions"] == []

    def test_portfolio_includes_position_market_value(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 200.0)

        execute_trade("default", "AAPL", "buy", 10.0, 100.0, cache)
        portfolio = get_portfolio("default", cache)

        assert portfolio["cash_balance"] == 9_000.0
        assert len(portfolio["positions"]) == 1
        pos = portfolio["positions"][0]
        assert pos["current_price"] == 200.0
        assert pos["market_value"] == 2_000.0
        assert pos["unrealized_pl"] == 1_000.0
        assert pos["unrealized_pl_percent"] == 100.0

    def test_portfolio_total_value_includes_cash_and_positions(self, tmp_db):
        cache = PriceCache()
        cache.update("AAPL", 200.0)

        execute_trade("default", "AAPL", "buy", 10.0, 100.0, cache)
        portfolio = get_portfolio("default", cache)

        # Cash 9000 + position market value 2000 = 11000
        assert portfolio["total_value"] == 11_000.0

    def test_unavailable_price_returns_null_fields(self, tmp_db):
        cache = PriceCache()  # no AAPL in cache

        execute_trade("default", "AAPL", "buy", 1.0, 100.0, cache)
        portfolio = get_portfolio("default", cache)

        pos = portfolio["positions"][0]
        assert pos["price_status"] == "unavailable"
        assert pos["current_price"] is None
        assert pos["market_value"] is None
        assert pos["unrealized_pl"] is None
