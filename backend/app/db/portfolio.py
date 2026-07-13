"""Portfolio business logic.

All trade execution, position management, and portfolio valuation live here.
This module is the single source of truth for financial rules.

The price_cache parameter expected by several functions is an
``app.market.cache.PriceCache`` instance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.market.cache import PriceCache

DEFAULT_USER_ID = "default"


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Trade execution
# ---------------------------------------------------------------------------

def execute_trade(
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    price_cache: PriceCache,
) -> dict[str, Any]:
    """Execute a market order and update cash/positions accordingly.

    Parameters
    ----------
    user_id : str
        User identifier (default: "default").
    ticker : str
        Ticker symbol, normalised to uppercase before storage.
    side : str
        "buy" or "sell".
    quantity : float
        Number of shares; must be > 0. Fractional shares are supported.
    price : float
        Execution price per share.
    price_cache : PriceCache
        Live price cache (used for valuation after the trade).

    Returns
    -------
    dict
        On success: ``{"trade": {...}, "cash_balance": float, "position": {...}}``
        On error: ``{"error": {"code": "...", "message": "..."}}``
    """
    from . import (
        delete_position,
        get_cash_balance,
        get_positions,
        record_snapshot,
        record_trade,
        upsert_position,
    )

    # Normalise
    ticker = ticker.upper().strip()

    # ---- Validation ----
    if quantity <= 0:
        return _error("INVALID_QUANTITY", "Quantity must be greater than zero.")

    if side not in ("buy", "sell"):
        return _error("INVALID_SIDE", "Side must be 'buy' or 'sell'.")

    if price is None or price <= 0:
        return _error("INVALID_PRICE", "Price must be a positive number.")

    cost = round(quantity * price, 2)

    if side == "buy":
        cash = get_cash_balance(user_id)
        if cash < cost:
            return _error(
                "INSUFFICIENT_CASH",
                f"Not enough cash to complete this buy order. "
                f"Required: ${cost:.2f}, available: ${cash:.2f}.",
            )

    elif side == "sell":
        positions = get_positions(user_id)
        held = next((p for p in positions if p["ticker"] == ticker), None)
        if held is None or held["quantity"] < quantity:
            owned = held["quantity"] if held else 0.0
            return _error(
                "INSUFFICIENT_SHARES",
                f"Not enough shares to complete this sell order. "
                f"Required: {quantity}, owned: {owned}.",
            )

    # ---- Execute ----
    # Record the trade first
    trade = record_trade(user_id, ticker, side, quantity, price)

    # Update cash
    with get_connection() as conn:
        if side == "buy":
            new_cash = cash - cost
        else:  # sell
            cash = get_cash_balance(user_id)
            new_cash = round(cash + cost, 2)

        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (new_cash, user_id),
        )
        conn.commit()

    # Update position
    if side == "buy":
        # Weighted-average cost
        positions = get_positions(user_id)
        held = next((p for p in positions if p["ticker"] == ticker), None)

        if held is None:
            new_qty = quantity
            new_avg = price
        else:
            prev_qty = held["quantity"]
            prev_avg = held["avg_cost"]
            total_qty = round(prev_qty + quantity, 8)
            new_avg = round((prev_qty * prev_avg + quantity * price) / total_qty, 8)
            new_qty = total_qty

        upsert_position(user_id, ticker, new_qty, new_avg)

    else:  # sell
        positions = get_positions(user_id)
        held = next((p for p in positions if p["ticker"] == ticker), None)
        assert held is not None  # validated above

        new_qty = round(held["quantity"] - quantity, 8)
        new_avg = held["avg_cost"]  # unchanged on sell

        if new_qty <= 0:
            delete_position(user_id, ticker)
        else:
            upsert_position(user_id, ticker, new_qty, new_avg)

    # Snapshot after trade
    total = _compute_total_value(user_id, price_cache)
    record_snapshot(user_id, total)

    # Fetch updated position
    positions = get_positions(user_id)
    updated_position = next((p for p in positions if p["ticker"] == ticker), None)

    return {
        "trade": trade,
        "cash_balance": new_cash,
        "position": dict(updated_position) if updated_position else None,
    }


# ---------------------------------------------------------------------------
# Portfolio valuation
# ---------------------------------------------------------------------------

def _compute_total_value(user_id: str, price_cache: PriceCache) -> float:
    """Compute total portfolio value: cash + sum(market_value for each position)."""
    from . import get_cash_balance, get_positions

    cash = get_cash_balance(user_id)
    positions = get_positions(user_id)
    pos_value = 0.0
    for pos in positions:
        price = price_cache.get_price(pos["ticker"])
        if price is not None:
            pos_value += round(pos["quantity"] * price, 2)
    return round(cash + pos_value, 2)


def get_portfolio(
    user_id: str = DEFAULT_USER_ID,
    price_cache: PriceCache | None = None,
) -> dict[str, Any]:
    """Return the full portfolio snapshot with live prices.

    Parameters
    ----------
    user_id : str
    price_cache : PriceCache | None
        If None, positions are returned without live valuation fields.

    Returns
    -------
    dict with keys:
        cash_balance (float)
        positions (list[dict]) with extra fields: current_price, market_value,
            unrealized_pl, unrealized_pl_percent
        total_value (float)
        unrealized_pl (float)
        timestamp (str, ISO-8601)
    """
    from . import get_cash_balance, get_positions

    user_id = user_id or DEFAULT_USER_ID
    cash_balance = get_cash_balance(user_id)
    positions = get_positions(user_id)
    now = datetime.now(timezone.utc).isoformat()

    enriched_positions: list[dict[str, Any]] = []
    total_unrealized_pl = 0.0
    total_market_value = 0.0

    for pos in positions:
        ticker = pos["ticker"]
        quantity = pos["quantity"]
        avg_cost = pos["avg_cost"]

        if price_cache is not None:
            pu = price_cache.get(ticker)
            if pu is not None:
                current_price = pu.price
                price_status = "available"
            else:
                current_price = None
                price_status = "unavailable"
        else:
            current_price = None
            price_status = "unavailable"

        if current_price is not None:
            market_value = round(quantity * current_price, 2)
            unrealized_pl = round(market_value - quantity * avg_cost, 2)
            unrealized_pl_percent = (
                round((current_price - avg_cost) / avg_cost * 100, 4)
                if avg_cost != 0
                else 0.0
            )
            total_unrealized_pl = round(total_unrealized_pl + unrealized_pl, 2)
            total_market_value = round(total_market_value + market_value, 2)
        else:
            market_value = None
            unrealized_pl = None
            unrealized_pl_percent = None

        enriched_positions.append({
            "ticker": ticker,
            "quantity": quantity,
            "avg_cost": avg_cost,
            "current_price": current_price,
            "price_status": price_status,
            "market_value": market_value,
            "unrealized_pl": unrealized_pl,
            "unrealized_pl_percent": unrealized_pl_percent,
        })

    total_value = round(cash_balance + total_market_value, 2)

    return {
        "cash_balance": cash_balance,
        "positions": enriched_positions,
        "total_value": total_value,
        "unrealized_pl": total_unrealized_pl,
        "timestamp": now,
    }


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

from .connection import get_connection  # noqa: E402  # pylint: disable=wrong-import-position
