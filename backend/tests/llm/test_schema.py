"""Tests for the LLM schema models."""

import pytest
from pydantic import ValidationError

from app.llm.schema import (
    ChatResponse,
    ErrorDetail,
    TradeAction,
    WatchlistChange,
)


class TestErrorDetail:
    def test_valid(self):
        e = ErrorDetail(code="INSUFFICIENT_CASH", message="Not enough cash.")
        assert e.code == "INSUFFICIENT_CASH"
        assert e.message == "Not enough cash."

    def test_serialization(self):
        e = ErrorDetail(code="FOO", message="Bar")
        assert e.model_dump() == {"code": "FOO", "message": "Bar"}

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ErrorDetail(code="ONLY_CODE")
        with pytest.raises(ValidationError):
            ErrorDetail(message="Only message")


class TestTradeAction:
    def test_executed_trade(self):
        t = TradeAction(
            ticker="AAPL",
            side="buy",
            quantity=2.5,
            status="executed",
            error=None,
        )
        assert t.ticker == "AAPL"
        assert t.side == "buy"
        assert t.quantity == 2.5
        assert t.status == "executed"
        assert t.error is None

    def test_failed_trade(self):
        err = ErrorDetail(code="INSUFFICIENT_CASH", message="Not enough cash.")
        t = TradeAction(
            ticker="TSLA",
            side="buy",
            quantity=10.0,
            status="failed",
            error=err,
        )
        assert t.status == "failed"
        assert t.error.code == "INSUFFICIENT_CASH"

    def test_invalid_side(self):
        with pytest.raises(ValidationError):
            TradeAction(ticker="AAPL", side="hold", quantity=1, status="executed")

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            TradeAction(ticker="AAPL", side="buy", quantity=1, status="pending")

    def test_serialization_round_trip(self):
        err = ErrorDetail(code="PRICE_UNAVAILABLE", message="No price data.")
        t = TradeAction(
            ticker="GOOGL",
            side="sell",
            quantity=3.0,
            status="failed",
            error=err,
        )
        data = t.model_dump()
        restored = TradeAction(**data)
        assert restored.ticker == "GOOGL"
        assert restored.error.code == "PRICE_UNAVAILABLE"


class TestWatchlistChange:
    def test_add_executed(self):
        w = WatchlistChange(action="add", ticker="NVDA", status="executed", error=None)
        assert w.action == "add"
        assert w.status == "executed"
        assert w.error is None

    def test_remove_failed(self):
        err = ErrorDetail(code="WATCHLIST_FULL", message="Max 30 tickers reached.")
        w = WatchlistChange(action="remove", ticker="AAPL", status="failed", error=err)
        assert w.action == "remove"
        assert w.status == "failed"
        assert w.error.code == "WATCHLIST_FULL"

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            WatchlistChange(action="toggle", ticker="AAPL", status="executed")

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            WatchlistChange(action="add", ticker="AAPL", status="success")


class TestChatResponse:
    def test_minimal_empty(self):
        r = ChatResponse(message="Hello!", trades=[], watchlist_changes=[])
        assert r.message == "Hello!"
        assert r.trades == []
        assert r.watchlist_changes == []

    def test_with_trades_and_watchlist(self):
        trade = TradeAction(ticker="AAPL", side="buy", quantity=1.0, status="executed")
        wc = WatchlistChange(action="add", ticker="MSFT", status="executed")
        r = ChatResponse(
            message="Done!",
            trades=[trade],
            watchlist_changes=[wc],
        )
        assert len(r.trades) == 1
        assert len(r.watchlist_changes) == 1
        assert r.trades[0].ticker == "AAPL"
        assert r.watchlist_changes[0].action == "add"

    def test_default_lists(self):
        """trades and watchlist_changes should default to empty lists."""
        r = ChatResponse(message="Hi")
        assert r.trades == []
        assert r.watchlist_changes == []

    def test_model_dump(self):
        r = ChatResponse(
            message="Bought AAPL.",
            trades=[
                TradeAction(
                    ticker="AAPL",
                    side="buy",
                    quantity=2.0,
                    status="executed",
                    error=None,
                )
            ],
            watchlist_changes=[],
        )
        data = r.model_dump()
        assert data["message"] == "Bought AAPL."
        assert len(data["trades"]) == 1
        assert data["trades"][0]["ticker"] == "AAPL"

    def test_model_dump_json_serializable(self):
        """The dumped dict must be JSON-serializable without errors."""
        import json

        r = ChatResponse(
            message="Test",
            trades=[
                TradeAction(
                    ticker="TSLA",
                    side="sell",
                    quantity=5.0,
                    status="failed",
                    error=ErrorDetail(code="INSUFFICIENT_SHARES", message="Not enough shares."),
                )
            ],
            watchlist_changes=[],
        )
        json_str = json.dumps(r.model_dump())
        assert "TSLA" in json_str
        assert "INSUFFICIENT_SHARES" in json_str
