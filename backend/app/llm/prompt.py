"""System-prompt builder for the FinAlly AI assistant.

Constructs the full prompt sent to the LLM on every chat request,
including portfolio context and conversation history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def format_price(price: float | None) -> str:
    """Format a price for the prompt, or return 'N/A' if unavailable."""
    return f"${price:.2f}" if price is not None else "N/A"


def format_position_line(
    ticker: str,
    quantity: float,
    avg_cost: float,
    current_price: float | None,
) -> str:
    """Format a single position as a one-line summary."""
    if current_price is None:
        return (
            f"  {ticker}: {quantity} shares @ avg ${avg_cost:.2f}, current price: N/A"
        )
    pl = (current_price - avg_cost) * quantity
    pl_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
    pl_sign = "+" if pl >= 0 else ""
    return (
        f"  {ticker}: {quantity} shares @ avg ${avg_cost:.2f}, "
        f"now {format_price(current_price)} "
        f"({pl_sign}{pl:.2f} / {pl_sign}{pl_pct:.2f}%)"
    )


def build_system_prompt(
    cash_balance: float,
    positions: list[dict],
    watchlist: list[dict],
    total_value: float,
    conversation_history: list[dict],
    current_time: str,
) -> str:
    """Build the system prompt for the FinAlly LLM assistant.

    Parameters
    ----------
    cash_balance:
        Available cash in dollars.
    positions:
        List of position dicts with keys: ticker, quantity, avg_cost, current_price.
    watchlist:
        List of watchlist item dicts with keys: ticker, price, change_percent.
    total_value:
        Total portfolio value (cash + positions).
    conversation_history:
        List of dicts with keys: role ("user" or "assistant"), content (str).
        At most the last 20 entries.
    current_time:
        ISO-8601 timestamp string for display.

    Returns
    -------
    str
        The full system prompt to send to the LLM.
    """
    lines = [
        "You are FinAlly, an AI-powered trading assistant embedded in a professional trading workstation.",
        "You have real-time access to the user's portfolio and market data.",
        "",
        "## Portfolio Context",
        f"  Cash available: ${cash_balance:,.2f}",
        f"  Total portfolio value: ${total_value:,.2f}",
        "",
        "## Positions",
    ]

    if positions:
        for p in positions:
            lines.append(format_position_line(
                ticker=p["ticker"],
                quantity=p["quantity"],
                avg_cost=p["avg_cost"],
                current_price=p.get("current_price"),
            ))
    else:
        lines.append("  (no open positions)")

    lines.extend(["", "## Watchlist (with live prices)"])
    if watchlist:
        for w in watchlist:
            ticker = w["ticker"]
            price_str = format_price(w.get("price"))
            change = w.get("change_percent")
            change_str = (
                f"{change:+.2f}%" if change is not None else "N/A"
            )
            lines.append(f"  {ticker}: {price_str} ({change_str})")
    else:
        lines.append("  (empty)")

    # Conversation history (last 20 turns)
    lines.append("")
    lines.append("## Conversation History")
    if conversation_history:
        for turn in conversation_history[-20:]:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            content = turn["content"].strip()
            lines.append(f"{role_label}: {content}")
    else:
        lines.append("  (no prior messages)")

    lines.extend([
        "",
        "## Your capabilities",
        "- Analyze portfolio composition, risk, and P&L",
        "- Suggest trades with reasoning",
        "- Execute trades and manage the watchlist when the user asks or agrees",
        "- Respond with valid JSON only — see below for the required schema",
        "",
        "## Response format",
        "You MUST respond with a single JSON object with exactly these fields:",
        '  {',
        '    "message": "<your conversational response to the user>",',
        '    "trades": [<trade objects, or empty array>],',
        '    "watchlist_changes": [<watchlist change objects, or empty array>]',
        '  }',
        "",
        "Trade object:",
        '  { "ticker": "AAPL", "side": "buy"|"sell", "quantity": 1.5, "status": "executed"|"failed", "error": null|{ "code": "...", "message": "..." } }',
        "",
        "Watchlist change object:",
        '  { "action": "add"|"remove", "ticker": "AAPL", "status": "executed"|"failed", "error": null|{ "code": "...", "message": "..." } }',
        "",
        "Rules:",
        "- Be concise and data-driven. Numbers speak for themselves.",
        "- Do not hallucinate prices; use the context provided above.",
        "- Only execute trades the user explicitly asks for.",
        "- trades and watchlist_changes must always be present as arrays (even if empty).",
        "- error must be null when status is 'executed'.",
        f"- Current time: {current_time}.",
    ])

    return "\n".join(lines)


def build_user_message(message: str, conversation_history: list[dict]) -> str:
    """Wrap the raw user message with any needed framing for the LLM."""
    return message.strip()
