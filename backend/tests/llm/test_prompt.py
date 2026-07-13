"""Tests for system-prompt building."""


from app.llm.prompt import build_system_prompt, format_position_line, format_price


class TestFormatPrice:
    def test_with_price(self):
        assert format_price(190.5) == "$190.50"

    def test_none(self):
        assert format_price(None) == "N/A"

    def test_rounds_correctly(self):
        assert format_price(123.456) == "$123.46"


class TestFormatPositionLine:
    def test_with_current_price(self):
        line = format_position_line(
            ticker="AAPL",
            quantity=10.0,
            avg_cost=180.0,
            current_price=190.0,
        )
        assert "AAPL" in line
        assert "10.0" in line
        assert "$180.00" in line
        assert "$190.00" in line
        assert "+" in line  # profit

    def test_without_current_price(self):
        line = format_position_line(
            ticker="NVDA",
            quantity=5.0,
            avg_cost=450.0,
            current_price=None,
        )
        assert "NVDA" in line
        assert "N/A" in line


class TestBuildSystemPrompt:
    def test_basic_structure(self):
        prompt = build_system_prompt(
            cash_balance=10_000.0,
            positions=[],
            watchlist=[],
            total_value=10_000.0,
            conversation_history=[],
            current_time="2026-07-10T12:00:00Z",
        )
        assert "FinAlly" in prompt
        assert "$10,000.00" in prompt
        assert "## Positions" in prompt
        assert "## Watchlist" in prompt
        assert "## Conversation History" in prompt

    def test_positions_section(self):
        prompt = build_system_prompt(
            cash_balance=5_000.0,
            positions=[
                {
                    "ticker": "AAPL",
                    "quantity": 10.0,
                    "avg_cost": 180.0,
                    "current_price": 190.0,
                }
            ],
            watchlist=[],
            total_value=6_900.0,
            conversation_history=[],
            current_time="2026-07-10T12:00:00Z",
        )
        assert "AAPL" in prompt
        assert "10.0" in prompt
        assert "$180.00" in prompt
        assert "$190.00" in prompt

    def test_watchlist_section(self):
        prompt = build_system_prompt(
            cash_balance=10_000.0,
            positions=[],
            watchlist=[
                {"ticker": "TSLA", "price": 250.0, "change_percent": 1.5},
                {"ticker": "NVDA", "price": 500.0, "change_percent": None},
            ],
            total_value=10_000.0,
            conversation_history=[],
            current_time="2026-07-10T12:00:00Z",
        )
        assert "TSLA" in prompt
        assert "NVDA" in prompt
        assert "$250.00" in prompt
        assert "+1.50%" in prompt or "1.50%" in prompt

    def test_conversation_history_section(self):
        prompt = build_system_prompt(
            cash_balance=10_000.0,
            positions=[],
            watchlist=[],
            total_value=10_000.0,
            conversation_history=[
                {"role": "user", "content": "Hello!"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            current_time="2026-07-10T12:00:00Z",
        )
        assert "Hello!" in prompt
        assert "Hi there!" in prompt

    def test_conversation_history_truncated_to_20(self):
        history = [{"role": "user", "content": f"msg{i}"} for i in range(25)]
        prompt = build_system_prompt(
            cash_balance=10_000.0,
            positions=[],
            watchlist=[],
            total_value=10_000.0,
            conversation_history=history,
            current_time="2026-07-10T12:00:00Z",
        )
        # Last 20 messages (indices 5-24) should be present
        assert "msg5" in prompt
        assert "msg24" in prompt
        # First 5 messages (indices 0-4) should NOT be present
        assert "msg0" not in prompt
        assert "msg4" not in prompt

    def test_response_format_section(self):
        prompt = build_system_prompt(
            cash_balance=10_000.0,
            positions=[],
            watchlist=[],
            total_value=10_000.0,
            conversation_history=[],
            current_time="2026-07-10T12:00:00Z",
        )
        # Prompt should contain the JSON field names and example structure
        assert '"message"' in prompt
        assert '"trades"' in prompt
        assert '"watchlist_changes"' in prompt
        assert "json_object" in prompt.lower() or "valid json" in prompt.lower()

    def test_current_time_included(self):
        ts = "2026-07-10T09:30:00+00:00"
        prompt = build_system_prompt(
            cash_balance=10_000.0,
            positions=[],
            watchlist=[],
            total_value=10_000.0,
            conversation_history=[],
            current_time=ts,
        )
        assert ts in prompt
