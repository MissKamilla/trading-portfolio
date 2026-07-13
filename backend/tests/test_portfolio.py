"""Tests for portfolio trade execution and P&L logic."""

from __future__ import annotations

import pytest

from app.db.portfolio import execute_trade, get_portfolio
from app.market.cache import PriceCache


class TestExecuteTradeValidation:
    """Test that execute_trade rejects invalid inputs correctly."""

    def test_quantity_zero_rejected(self, tmp_db: str) -> None:
        """Zero quantity must be rejected."""
        cache = PriceCache()
        result = execute_trade("default", "AAPL", "buy", 0, 100.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INVALID_QUANTITY"

    def test_quantity_negative_rejected(self, tmp_db: str) -> None:
        """Negative quantity must be rejected."""
        cache = PriceCache()
        result = execute_trade("default", "AAPL", "buy", -1.0, 100.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INVALID_QUANTITY"

    def test_invalid_side_rejected(self, tmp_db: str) -> None:
        """Invalid side must be rejected."""
        cache = PriceCache()
        for bad_side in ("hold", "HOLD", "Buy", "", "short"):
            result = execute_trade("default", "AAPL", bad_side, 1.0, 100.0, cache)
            assert "error" in result, f"Expected error for side={bad_side!r}"
            assert result["error"]["code"] == "INVALID_SIDE"

    def test_price_zero_rejected(self, tmp_db: str) -> None:
        """Zero price must be rejected."""
        cache = PriceCache()
        result = execute_trade("default", "AAPL", "buy", 1.0, 0.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INVALID_PRICE"

    def test_price_negative_rejected(self, tmp_db: str) -> None:
        """Negative price must be rejected."""
        cache = PriceCache()
        result = execute_trade("default", "AAPL", "buy", 1.0, -50.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INVALID_PRICE"

    def test_price_none_rejected(self, tmp_db: str) -> None:
        """None price must be rejected."""
        cache = PriceCache()
        result = execute_trade("default", "AAPL", "buy", 1.0, None, cache)  # type: ignore
        assert "error" in result
        assert result["error"]["code"] == "INVALID_PRICE"


class TestExecuteTradeInsufficientFunds:
    """Test that insufficient cash/shares are correctly rejected."""

    def test_buy_insufficient_cash_rejected(self, tmp_db: str) -> None:
        """Buying more than available cash must be rejected."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        # Default cash is $10,000. Buy 100 shares at $190 = $19,000 → too expensive.
        result = execute_trade("default", "AAPL", "buy", 100.0, 190.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INSUFFICIENT_CASH"

    def test_sell_no_position_rejected(self, tmp_db: str) -> None:
        """Selling a ticker with no position must be rejected."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        result = execute_trade("default", "AAPL", "sell", 1.0, 190.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INSUFFICIENT_SHARES"

    def test_sell_more_than_owned_rejected(self, tmp_db: str) -> None:
        """Selling more shares than owned must be rejected."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        # First buy 1 share
        result = execute_trade("default", "AAPL", "buy", 1.0, 190.0, cache)
        assert "trade" in result
        # Now try to sell 5 shares (only own 1)
        result = execute_trade("default", "AAPL", "sell", 5.0, 190.0, cache)
        assert "error" in result
        assert result["error"]["code"] == "INSUFFICIENT_SHARES"


class TestExecuteTradeBuy:
    """Test successful buy executions."""

    def test_buy_shares_cash_decreases(self, tmp_db: str) -> None:
        """After buying, cash_balance must reflect the purchase."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        result = execute_trade("default", "AAPL", "buy", 1.0, 190.0, cache)
        assert "trade" in result
        # Bought 1 share at $190: $10,000 - $190 = $9,810
        assert result["cash_balance"] == 9810.0

    def test_buy_creates_position(self, tmp_db: str) -> None:
        """After buying a new ticker, a position must exist."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        result = execute_trade("default", "AAPL", "buy", 1.0, 190.0, cache)
        assert result["position"]["ticker"] == "AAPL"
        assert result["position"]["quantity"] == 1.0
        assert result["position"]["avg_cost"] == 190.0

    def test_buy_fractional_shares(self, tmp_db: str) -> None:
        """Fractional share purchases must be stored and valued correctly."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        result = execute_trade("default", "AAPL", "buy", 0.5, 190.0, cache)
        assert "trade" in result
        assert result["position"]["quantity"] == 0.5

    def test_buy_updates_existing_position_weighted_avg(self, tmp_db: str) -> None:
        """Multiple buys of the same ticker must use weighted-average cost."""
        cache = PriceCache()
        cache.update("AAPL", 100.0)
        # Buy 1 share at $100
        r1 = execute_trade("default", "AAPL", "buy", 1.0, 100.0, cache)
        assert r1["position"]["avg_cost"] == 100.0
        assert r1["position"]["quantity"] == 1.0

        # Buy another 1 share at $200
        cache.update("AAPL", 200.0)
        r2 = execute_trade("default", "AAPL", "buy", 1.0, 200.0, cache)
        # Weighted avg = (1*100 + 1*200) / 2 = 150
        assert r2["position"]["quantity"] == 2.0
        assert r2["position"]["avg_cost"] == 150.0

    def test_buy_updates_cash_after_weighted_avg(self, tmp_db: str) -> None:
        """Cash must decrease correctly after second buy (weighted avg)."""
        cache = PriceCache()
        cache.update("AAPL", 100.0)
        execute_trade("default", "AAPL", "buy", 1.0, 100.0, cache)
        cache.update("AAPL", 200.0)
        r2 = execute_trade("default", "AAPL", "buy", 1.0, 200.0, cache)
        # $10,000 - $100 - $200 = $9,700
        assert r2["cash_balance"] == 9700.0


class TestExecuteTradeSell:
    """Test successful sell executions."""

    def test_sell_reduces_position_quantity(self, tmp_db: str) -> None:
        """Partial sell must reduce quantity but keep avg_cost unchanged."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        # Buy 5 shares
        execute_trade("default", "AAPL", "buy", 5.0, 190.0, cache)
        # Sell 3 shares
        cache.update("AAPL", 195.0)
        r = execute_trade("default", "AAPL", "sell", 3.0, 195.0, cache)
        assert r["position"]["quantity"] == 2.0
        assert r["position"]["avg_cost"] == 190.0  # avg_cost unchanged on sell

    def test_sell_increases_cash(self, tmp_db: str) -> None:
        """Selling shares must increase cash_balance."""
        cache = PriceCache()
        cache.update("AAPL", 100.0)
        execute_trade("default", "AAPL", "buy", 1.0, 100.0, cache)
        cache.update("AAPL", 150.0)
        r = execute_trade("default", "AAPL", "sell", 1.0, 150.0, cache)
        # Bought for $100, sold for $150: $10,000 - $100 + $150 = $10,050
        assert r["cash_balance"] == 10050.0

    def test_sell_full_position_deletes_it(self, tmp_db: str) -> None:
        """Selling the last share must delete the position row (return None)."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        execute_trade("default", "AAPL", "buy", 2.0, 190.0, cache)
        cache.update("AAPL", 195.0)
        r = execute_trade("default", "AAPL", "sell", 2.0, 195.0, cache)
        # Position should be None (row deleted from DB per PLAN.md spec)
        assert r["position"] is None

    def test_sell_fractional_shares(self, tmp_db: str) -> None:
        """Fractional sell must work correctly."""
        cache = PriceCache()
        cache.update("AAPL", 100.0)
        execute_trade("default", "AAPL", "buy", 1.0, 100.0, cache)
        cache.update("AAPL", 200.0)
        r = execute_trade("default", "AAPL", "sell", 0.25, 200.0, cache)
        assert r["position"]["quantity"] == 0.75


class TestGetPortfolio:
    """Test get_portfolio valuation."""

    def test_portfolio_has_required_fields(self, tmp_db: str) -> None:
        """get_portfolio must return all required top-level fields."""
        cache = PriceCache()
        portfolio = get_portfolio("default", cache)
        assert "cash_balance" in portfolio
        assert "positions" in portfolio
        assert "total_value" in portfolio
        assert "unrealized_pl" in portfolio
        assert "timestamp" in portfolio

    def test_portfolio_cash_is_default_10k(self, tmp_db: str) -> None:
        """Fresh portfolio must start with $10,000 cash."""
        cache = PriceCache()
        portfolio = get_portfolio("default", cache)
        assert portfolio["cash_balance"] == 10_000.0

    def test_portfolio_with_position_has_live_price(self, tmp_db: str) -> None:
        """Position must include live current_price from the cache."""
        cache = PriceCache()
        cache.update("AAPL", 195.0)
        execute_trade("default", "AAPL", "buy", 10.0, 190.0, cache)
        # Update price to 195
        portfolio = get_portfolio("default", cache)
        aapl = next((p for p in portfolio["positions"] if p["ticker"] == "AAPL"), None)
        assert aapl is not None
        assert aapl["current_price"] == 195.0

    def test_portfolio_unrealized_pl_correct(self, tmp_db: str) -> None:
        """Unrealized P&L = (current_price - avg_cost) * quantity."""
        cache = PriceCache()
        cache.update("AAPL", 200.0)
        execute_trade("default", "AAPL", "buy", 10.0, 190.0, cache)
        portfolio = get_portfolio("default", cache)
        aapl = next((p for p in portfolio["positions"] if p["ticker"] == "AAPL"), None)
        assert aapl is not None
        # (200 - 190) * 10 = 100
        assert aapl["unrealized_pl"] == pytest.approx(100.0, rel=1e-6)
        assert aapl["unrealized_pl_percent"] == pytest.approx(5.263157, rel=1e-3)

    def test_portfolio_total_value_includes_cash_and_positions(self, tmp_db: str) -> None:
        """total_value must equal cash + sum of market_value of all positions."""
        cache = PriceCache()
        cache.update("AAPL", 200.0)
        execute_trade("default", "AAPL", "buy", 10.0, 190.0, cache)
        portfolio = get_portfolio("default", cache)
        # $10,000 cash - $1,900 cost + 10 * $200 = $10,100
        assert portfolio["total_value"] == 10_100.0

    def test_portfolio_market_value(self, tmp_db: str) -> None:
        """market_value must equal current_price * quantity."""
        cache = PriceCache()
        cache.update("AAPL", 250.0)
        execute_trade("default", "AAPL", "buy", 10.0, 100.0, cache)
        portfolio = get_portfolio("default", cache)
        aapl = next((p for p in portfolio["positions"] if p["ticker"] == "AAPL"), None)
        assert aapl["market_value"] == 2500.0  # 250 * 10


class TestTickerNormalization:
    """Test that tickers are normalized to uppercase."""

    def test_ticker_uppercase_stored(self, tmp_db: str) -> None:
        """Mixed-case ticker must be stored as uppercase."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        result = execute_trade("default", "aapl", "buy", 1.0, 190.0, cache)
        assert result["trade"]["ticker"] == "AAPL"
        assert result["position"]["ticker"] == "AAPL"

    def test_ticker_uppercase_sell(self, tmp_db: str) -> None:
        """Mixed-case ticker in sell must match stored uppercase ticker."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        execute_trade("default", "AAPL", "buy", 1.0, 190.0, cache)
        cache.update("AAPL", 195.0)
        result = execute_trade("default", "aapl", "sell", 1.0, 195.0, cache)
        # Position is None when fully sold (row deleted from DB per PLAN.md)
        assert result["position"] is None
