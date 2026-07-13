"""Deterministic mock LLM responses for development and testing.

Used when LLM_MOCK=true, when no OpenRouter key is present,
or when the real LLM call fails or times out.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import ChatResponse
else:
    from .schema import ErrorDetail  # noqa: F401


# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------

def _has_word(msg: str, *words: str) -> bool:
    """Return True if any single-word token matches, or any multi-word phrase appears."""
    for kw in words:
        if " " in kw:
            if kw in msg:
                return True
        else:
            if re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", msg):
                return True
    return False


def _extract_ticker(text: str) -> str | None:
    """Extract the first uppercase ticker symbol (2-5 letters) from text."""
    match = re.search(r"\b([A-Z]{2,5})\b", text)
    return match.group(1) if match else None


def _extract_quantity(text: str) -> float | None:
    """Extract the first positive numeric quantity from text."""
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _build_trade_response(
    ticker: str,
    side: str,
    quantity: float,
    cash_balance: float,
    current_price: float | None,
) -> dict:
    """Build a trade item dict with either executed or failed status."""
    cost = (quantity or 0) * (current_price or 0)
    if side == "buy":
        can_execute = (
            current_price is not None
            and quantity is not None
            and quantity > 0
            and cost <= cash_balance
        )
        fail_code = "INSUFFICIENT_CASH"
        fail_msg = "Not enough cash to complete this buy order."
    else:
        can_execute = current_price is not None and quantity is not None and quantity > 0
        fail_code = "PRICE_UNAVAILABLE"
        fail_msg = "Price data temporarily unavailable."

    if can_execute:
        return {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "status": "executed",
            "error": None,
        }
    return {
        "ticker": ticker,
        "side": side,
        "quantity": quantity or 0,
        "status": "failed",
        "error": {
            "code": "PRICE_UNAVAILABLE" if current_price is None else fail_code,
            "message": fail_msg if current_price is not None else fail_msg,
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_mock_response(
    user_message: str,
    cash_balance: float,
    prices: dict[str, float],
    positions: list[dict],
    watchlist: list[str],
) -> "ChatResponse":
    """Build a deterministic mock ChatResponse based on the user's message.

    Parameters
    ----------
    user_message:
        The raw message the user sent.
    cash_balance:
        Current cash balance for context-aware responses.
    prices:
        Map of ticker -> current price.
    positions:
        List of position dicts (ticker, quantity, avg_cost, current_price, ...).
    watchlist:
        List of currently watched tickers.

    Returns
    -------
    ChatResponse
        A fully-populated structured response matching the schema.
    """
    from .schema import ChatResponse, ErrorDetail, TradeAction, WatchlistChange

    msg_lower = user_message.lower().strip()
    position_tickers = {p["ticker"].upper() for p in positions}
    watchlist_set = {t.upper() for t in watchlist}
    all_tickers = set(prices.keys())

    # ------------------------------------------------------------------
    # WATCHLIST REMOVE  (specific intent — checked before generic sell)
    # ------------------------------------------------------------------
    if _has_word(msg_lower, "remove", "unwatch", "stop watching"):
        ticker = _extract_ticker(user_message)
        if ticker:
            ticker = ticker.upper()
            if ticker not in watchlist_set:
                return ChatResponse(
                    message=f"{ticker} is not in your watchlist.",
                    trades=[],
                    watchlist_changes=[],
                )
            return ChatResponse(
                message=f"Removed {ticker} from your watchlist.",
                trades=[],
                watchlist_changes=[
                    WatchlistChange(
                        action="remove", ticker=ticker, status="executed", error=None
                    )
                ],
            )
        return ChatResponse(
            message="Which ticker would you like to remove from your watchlist?",
            trades=[],
            watchlist_changes=[],
        )

    # ------------------------------------------------------------------
    # WATCHLIST ADD  (specific intent — checked before generic buy)
    # ------------------------------------------------------------------
    # "add" is checked here first (before the generic buy branch) so that
    # "add xyz to watchlist" triggers watchlist-add, not a buy of xyz.
    if _has_word(msg_lower, "add", "watch", "track"):
        ticker = _extract_ticker(user_message)
        if ticker:
            ticker = ticker.upper()
            if ticker in watchlist_set:
                return ChatResponse(
                    message=f"{ticker} is already in your watchlist.",
                    trades=[],
                    watchlist_changes=[],
                )
            if len(watchlist) >= 30:
                return ChatResponse(
                    message=(
                        "Your watchlist is full (30 tickers max). "
                        "Please remove a ticker before adding a new one."
                    ),
                    trades=[],
                    watchlist_changes=[],
                )
            return ChatResponse(
                message=f"Added {ticker} to your watchlist.",
                trades=[],
                watchlist_changes=[
                    WatchlistChange(action="add", ticker=ticker, status="executed", error=None)
                ],
            )
        return ChatResponse(
            message="Which ticker would you like to add to your watchlist?",
            trades=[],
            watchlist_changes=[],
        )

    # ------------------------------------------------------------------
    # BUY intent  (word-boundary match avoids false positives)
    # ------------------------------------------------------------------
    if _has_word(msg_lower, "buy", "purchase", "acquire", "acquisition", "long"):
        ticker = _extract_ticker(user_message)
        quantity = _extract_quantity(user_message)

        if ticker:
            ticker = ticker.upper()
            current_price = prices.get(ticker)
            position_exists = ticker in position_tickers
            in_watchlist = ticker in watchlist_set

            trade_item = _build_trade_response(
                ticker=ticker,
                side="buy",
                quantity=quantity or 1.0,
                cash_balance=cash_balance,
                current_price=current_price,
            )
            trade = TradeAction(**trade_item)

            if trade.status == "executed":
                if quantity and quantity > 1:
                    message = (
                        f"Bought {quantity} shares of {ticker} at "
                        f"${current_price:.2f} per share."
                    )
                else:
                    message = (
                        f"Bought 1 share of {ticker} at ${current_price:.2f}. "
                        f"You {'now hold a position' if not position_exists else 'have added to your position'}."
                    )
                if not in_watchlist and ticker in all_tickers:
                    message += f" I've also added {ticker} to your watchlist."
                    wc = WatchlistChange(
                        action="add", ticker=ticker, status="executed", error=None
                    )
                else:
                    wc = None
            else:
                message = (
                    f"I tried to buy {quantity or 1} share{'s' if (quantity or 0) != 1 else ''} "
                    f"of {ticker} but encountered an issue: {trade.error.message}"
                )
                wc = None

            watchlist_changes = [wc] if wc else []
            return ChatResponse(message=message, trades=[trade], watchlist_changes=watchlist_changes)

        # No ticker detected — generic response
        return ChatResponse(
            message=(
                "I'd be happy to help you buy shares. Could you tell me which ticker "
                "you'd like to purchase and how many shares? For example: 'Buy 2 shares of AAPL'."
            ),
            trades=[],
            watchlist_changes=[],
        )

    # ------------------------------------------------------------------
    # SELL intent
    # ------------------------------------------------------------------
    if _has_word(msg_lower, "sell", "liquidate"):
        ticker = _extract_ticker(user_message)
        quantity = _extract_quantity(user_message)

        if ticker:
            ticker = ticker.upper()
            current_price = prices.get(ticker)
            held = next((p for p in positions if p["ticker"].upper() == ticker), None)
            held_qty = held["quantity"] if held else 0

            if held and quantity and quantity > held_qty:
                return ChatResponse(
                    message=(
                        f"You only hold {held_qty} share{'s' if held_qty != 1 else ''} of {ticker}, "
                        f"so I can't sell {quantity}. Would you like to sell "
                        f"{min(quantity, held_qty):.4g} shares or fewer instead?"
                    ),
                    trades=[
                        TradeAction(
                            ticker=ticker,
                            side="sell",
                            quantity=quantity,
                            status="failed",
                            error=ErrorDetail(
                                code="INSUFFICIENT_SHARES",
                                message=f"You only hold {held_qty} share{'s' if held_qty != 1 else ''}.",
                            ),
                        )
                    ],
                    watchlist_changes=[],
                )

            trade_item = _build_trade_response(
                ticker=ticker,
                side="sell",
                quantity=quantity or held_qty if held else 0,
                cash_balance=cash_balance,
                current_price=current_price,
            )
            trade = TradeAction(**trade_item)

            if trade.status == "executed":
                message = (
                    f"Sold {trade.quantity} share{'s' if trade.quantity != 1 else ''} "
                    f"of {ticker} at ${current_price:.2f}."
                )
            else:
                message = (
                    f"You don't have a position in {ticker} to sell."
                    if not held
                    else (
                        f"I tried to sell {quantity or held_qty} shares of {ticker} "
                        f"but encountered an issue: {trade.error.message}"
                    )
                )
            return ChatResponse(message=message, trades=[trade], watchlist_changes=[])

        return ChatResponse(
            message=(
                "I can help you sell. Please tell me which ticker you'd like to sell "
                "and how many shares. For example: 'Sell 3 shares of TSLA'."
            ),
            trades=[],
            watchlist_changes=[],
        )

    # ------------------------------------------------------------------
    # PORTFOLIO / POSITION analysis
    # ------------------------------------------------------------------
    if _has_word(msg_lower, "portfolio", "position", "holdings", "performance", "pnl", "p&l"):
        total_value = sum(
            p["current_price"] * p["quantity"] for p in positions
        ) + cash_balance
        unrealized_pl = sum(
            (p["current_price"] - p["avg_cost"]) * p["quantity"]
            for p in positions
        )

        if not positions:
            return ChatResponse(
                message=(
                    f"Your portfolio is currently empty. You have "
                    f"${cash_balance:,.2f} in cash. "
                    f"Would you like to make a trade?"
                ),
                trades=[],
                watchlist_changes=[],
            )

        lines = [f"Portfolio value: ${total_value:,.2f} (cash: ${cash_balance:,.2f})."]
        for p in positions:
            pl = (p["current_price"] - p["avg_cost"]) * p["quantity"]
            pl_pct = (
                (p["current_price"] - p["avg_cost"]) / p["avg_cost"] * 100
                if p["avg_cost"] > 0
                else 0
            )
            direction = "+" if pl >= 0 else ""
            lines.append(
                f"  {p['ticker']}: {p['quantity']} shares @ ${p['avg_cost']:.2f} avg "
                f"-> ${p['current_price']:.2f} now ({direction}{pl:.2f} / {direction}{pl_pct:.2f}%)"
            )
        lines.append(f"Total unrealized P&L: {direction}{unrealized_pl:,.2f}")
        return ChatResponse(
            message="\n".join(lines),
            trades=[],
            watchlist_changes=[],
        )

    # ------------------------------------------------------------------
    # Default: conversational response with portfolio summary
    # ------------------------------------------------------------------
    total_value = sum(p["current_price"] * p["quantity"] for p in positions) + cash_balance
    return ChatResponse(
        message=(
            f"Hi! I'm FinAlly, your AI trading assistant. "
            f"Your portfolio is worth ${total_value:,.2f} with ${cash_balance:,.2f} in cash. "
            f"You hold {len(positions)} position{'s' if len(positions) != 1 else ''}. "
            f"Ask me to analyze your portfolio, make trades, or manage your watchlist!"
        ),
        trades=[],
        watchlist_changes=[],
    )
