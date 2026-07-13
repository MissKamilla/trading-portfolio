"""Tests for the ChatClient — fallback behavior, mock mode, and structured parsing."""

import os
from unittest.mock import patch

import pytest

from app.llm.client import ChatClient
from app.llm.prompt import build_system_prompt
from app.llm.schema import ChatResponse

# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return ChatClient(system_prompt_fn=build_system_prompt)


@pytest.fixture
def context():
    return dict(
        message="Hello!",
        cash_balance=10_000.0,
        positions=[],
        watchlist=[],
        total_value=10_000.0,
        conversation_history=[],
        current_time="2026-07-10T12:00:00Z",
    )


# ---------------------------------------------------------------------------
# _is_mock_mode
# ---------------------------------------------------------------------------

class TestIsMockMode:
    def test_true_when_flag_set(self):
        with patch.dict(os.environ, {"LLM_MOCK": "true"}, clear=False):
            # Clear OPENROUTER_API_KEY to avoid environment bleed
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
                # Need to re-import to pick up patched env
                import importlib

                import app.llm.client as client_mod
                importlib.reload(client_mod)
                assert client_mod._is_mock_mode() is True

    def test_true_when_no_api_key(self):
        with patch.dict(os.environ, {"LLM_MOCK": "false", "OPENROUTER_API_KEY": ""}):
            import importlib

            import app.llm.client as client_mod
            importlib.reload(client_mod)
            assert client_mod._is_mock_mode() is True

    def test_false_when_key_present_and_mock_off(self):
        with patch.dict(os.environ, {"LLM_MOCK": "false", "OPENROUTER_API_KEY": "sk-or-xxx"}):
            import importlib

            import app.llm.client as client_mod
            importlib.reload(client_mod)
            assert client_mod._is_mock_mode() is False


# ---------------------------------------------------------------------------
# _get_model
# ---------------------------------------------------------------------------

class TestGetModel:
    def test_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-xxx"}):
                import importlib

                import app.llm.client as client_mod
                importlib.reload(client_mod)
                assert "gpt-oss" in client_mod._get_model()

    def test_custom_model(self):
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "openrouter/anthropic/claude-3"}):
            import importlib

            import app.llm.client as client_mod
            importlib.reload(client_mod)
            assert client_mod._get_model() == "openrouter/anthropic/claude-3"


# ---------------------------------------------------------------------------
# ChatClient.chat — mock mode (the primary path in dev/testing)
# ---------------------------------------------------------------------------

class TestChatMockMode:
    @pytest.mark.asyncio
    async def test_mock_reply_basic(self, client, context):
        # Ensure mock mode by clearing key
        with patch.dict(os.environ, {"LLM_MOCK": "true", "OPENROUTER_API_KEY": ""}):
            response = await client.chat(**context)
            assert isinstance(response, ChatResponse)
            assert isinstance(response.message, str)
            assert isinstance(response.trades, list)
            assert isinstance(response.watchlist_changes, list)

    @pytest.mark.asyncio
    async def test_mock_reply_buy_with_price(self, client):
        with patch.dict(os.environ, {"LLM_MOCK": "true", "OPENROUTER_API_KEY": ""}):
            response = await client.chat(
                message="Buy 2 shares of AAPL",
                cash_balance=10_000.0,
                positions=[],
                watchlist=[{"ticker": "AAPL", "price": 190.0, "change_percent": 0.5}],
                total_value=10_000.0,
                conversation_history=[],
                current_time="2026-07-10T12:00:00Z",
            )
            assert len(response.trades) == 1
            assert response.trades[0].ticker == "AAPL"
            assert response.trades[0].quantity == 2.0
            assert response.trades[0].side == "buy"
            assert response.trades[0].status == "executed"

    @pytest.mark.asyncio
    async def test_mock_reply_insufficient_cash(self, client):
        with patch.dict(os.environ, {"LLM_MOCK": "true", "OPENROUTER_API_KEY": ""}):
            response = await client.chat(
                message="Buy 100 shares of AAPL",
                cash_balance=100.0,
                positions=[],
                watchlist=[{"ticker": "AAPL", "price": 190.0, "change_percent": 0.0}],
                total_value=100.0,
                conversation_history=[],
                current_time="2026-07-10T12:00:00Z",
            )
            assert len(response.trades) == 1
            assert response.trades[0].status == "failed"
            assert response.trades[0].error.code == "INSUFFICIENT_CASH"

    @pytest.mark.asyncio
    async def test_mock_reply_portfolio_query(self, client):
        with patch.dict(os.environ, {"LLM_MOCK": "true", "OPENROUTER_API_KEY": ""}):
            response = await client.chat(
                message="How is my portfolio?",
                cash_balance=5_000.0,
                positions=[
                    {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 180.0, "current_price": 190.0}
                ],
                watchlist=[{"ticker": "AAPL", "price": 190.0, "change_percent": 0.5}],
                total_value=6_900.0,
                conversation_history=[],
                current_time="2026-07-10T12:00:00Z",
            )
            assert len(response.trades) == 0
            assert isinstance(response.message, str)
            assert len(response.message) > 0

    @pytest.mark.asyncio
    async def test_mock_reply_watchlist_add(self, client):
        with patch.dict(os.environ, {"LLM_MOCK": "true", "OPENROUTER_API_KEY": ""}):
            response = await client.chat(
                message="Add NVDA to my watchlist",
                cash_balance=10_000.0,
                positions=[],
                watchlist=[],
                total_value=10_000.0,
                conversation_history=[],
                current_time="2026-07-10T12:00:00Z",
            )
            assert len(response.watchlist_changes) == 1
            assert response.watchlist_changes[0].action == "add"
            assert response.watchlist_changes[0].ticker == "NVDA"
            assert response.watchlist_changes[0].status == "executed"


# ---------------------------------------------------------------------------
# ChatClient._parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json(self):
        raw = '{"message": "Hello!", "trades": [], "watchlist_changes": []}'
        r = ChatClient._parse_response(raw)
        assert r.message == "Hello!"
        assert r.trades == []
        assert r.watchlist_changes == []

    def test_with_trade(self):
        raw = '{"message": "Bought AAPL", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1.0, "status": "executed", "error": null}], "watchlist_changes": []}'
        r = ChatClient._parse_response(raw)
        assert len(r.trades) == 1
        assert r.trades[0].ticker == "AAPL"

    def test_invalid_json_raises(self):
        raw = "this is not json"
        with pytest.raises(ValueError, match="not valid JSON"):
            ChatClient._parse_response(raw)
