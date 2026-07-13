"""FinAlly FastAPI application — main entry point."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles

from app.market import PriceCache, create_market_data_source, create_stream_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state (set during lifespan)
# ---------------------------------------------------------------------------
price_cache: PriceCache | None = None
_market_source: Any = None
_snapshot_task: asyncio.Task | None = None
_cleanup_task: asyncio.Task | None = None


# ===========================================================================
# Background tasks
# ===========================================================================

async def _snapshot_loop(cache: PriceCache) -> None:
    """Record a portfolio snapshot every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        try:
            _record_snapshot(cache)
        except Exception as exc:
            logger.warning("Snapshot write failed (will retry): %s", exc)


async def _cleanup_loop() -> None:
    """Remove portfolio_snapshots older than 7 days, once per day."""
    while True:
        await asyncio.sleep(86400)
        try:
            _run_cleanup()
        except Exception as exc:
            logger.warning("Snapshot cleanup failed (will retry): %s", exc)


def _record_snapshot(cache: PriceCache) -> None:
    """Write a single portfolio snapshot to the DB (no-op if DB not ready)."""
    try:
        from app.db import get_or_create_user, get_positions, record_snapshot

        user = get_or_create_user()
        positions = get_positions(user["id"])
        cash = user["cash_balance"]

        positions_value = 0.0
        for pos in positions:
            pu = cache.get(pos["ticker"])
            if pu is not None:
                positions_value += pu.price * pos["quantity"]

        total_value = cash + positions_value
        record_snapshot(user["id"], total_value)
        logger.debug("Portfolio snapshot recorded: total_value=%.2f", total_value)
    except ImportError:
        pass  # DB not ready yet


def _run_cleanup() -> None:
    """Delete portfolio_snapshots older than 7 days (no-op if DB not ready)."""
    try:
        from app.db import cleanup_old_snapshots
        removed = cleanup_old_snapshots(days=7)
        if removed:
            logger.info("Removed %d stale portfolio snapshots.", removed)
    except ImportError:
        pass  # DB not ready yet


# ===========================================================================
# Lifespan
# ===========================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global price_cache, _market_source, _snapshot_task, _cleanup_task

    # ---- Startup ----
    try:
        from app.db import init_db
        init_db()
        logger.info("Database initialised.")
    except ImportError:
        logger.warning("app.db not available yet — skipping DB init.")

    price_cache = PriceCache()
    app.state.price_cache = price_cache

    default_tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
    try:
        _market_source = create_market_data_source(price_cache)
        await _market_source.start(default_tickers)
        app.state.market_source = _market_source
        logger.info("Market data source started (tickers: %s).", default_tickers)
    except Exception as exc:
        logger.error("Failed to start market data source: %s", exc)

    _snapshot_task = asyncio.create_task(_snapshot_loop(price_cache))
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("Background tasks started.")

    # Wire up LLM router dependencies now that app state is ready
    _configure_llm_router()

    # Mount SSE streaming router now that price_cache exists
    app.include_router(create_stream_router(price_cache), tags=["streaming"])

    # Wire in the LLM chat router (prefix=/api → POST /api/chat)
    try:
        from app.llm import chat_router
        app.include_router(chat_router)
    except ImportError:
        logger.warning("app.llm not available — chat endpoint will not be mounted.")

    # Mount static files (Next.js build) once app is fully initialised
    _mount_static()

    yield

    # ---- Shutdown ----
    if _snapshot_task:
        _snapshot_task.cancel()
    if _cleanup_task:
        _cleanup_task.cancel()
    if _market_source:
        await _market_source.stop()
    logger.info("FinAlly shutdown complete.")


# ===========================================================================
# FastAPI app
# ===========================================================================

app = FastAPI(
    title="FinAlly API",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["system"])
async def health() -> dict:
    """Lightweight health check for Docker / load balancers."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

@app.get("/api/watchlist", tags=["watchlist"])
async def get_watchlist() -> dict:
    """Return the user's watchlist with live prices."""
    try:
        from app.db import get_watchlist as _get_watchlist
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Watchlist service not ready."},
        )

    if price_cache is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Price cache not ready.")

    raw_items = _get_watchlist()
    result = []
    for item in raw_items:
        ticker = item["ticker"]
        pu = price_cache.get(ticker)
        if pu is not None:
            result.append({
                "ticker": ticker,
                "price": pu.price,
                "previous_price": pu.previous_price,
                "change": pu.change,
                "change_percent": pu.change_percent,
                "direction": pu.direction,
                "price_status": "available",
                "timestamp": pu.timestamp,
            })
        else:
            result.append({
                "ticker": ticker,
                "price": None,
                "previous_price": None,
                "change": None,
                "change_percent": None,
                "direction": None,
                "price_status": "unavailable",
                "timestamp": None,
            })
    return {"items": result}


@app.post("/api/watchlist", status_code=status.HTTP_200_OK, tags=["watchlist"])
async def add_watchlist_ticker(body: dict | None = None) -> dict:
    """Add a ticker to the watchlist.

    Body: ``{"ticker": "pypl"}``
    """
    ticker_raw = (body or {}).get("ticker") if body else None
    if not ticker_raw or not isinstance(ticker_raw, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TICKER", "message": "Ticker is required."},
        )

    ticker_normalized = ticker_raw.strip().upper()
    if not ticker_normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TICKER", "message": "Ticker cannot be empty."},
        )

    try:
        from app.db import add_to_watchlist
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Watchlist service not ready."},
        )

    result = add_to_watchlist(ticker_normalized)
    if not result["added"]:
        code = result.get("error", "UNKNOWN")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": _code_to_message(code)},
        )

    # Start pricing the new ticker
    if _market_source is not None:
        await _market_source.add_ticker(ticker_normalized)

    return {"ticker": ticker_normalized, "added": True}


@app.delete("/api/watchlist/{ticker}", tags=["watchlist"])
async def remove_watchlist_ticker(ticker: str) -> dict:
    """Remove a ticker from the watchlist."""
    ticker_normalized = ticker.strip().upper()

    try:
        from app.db import remove_from_watchlist
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Watchlist service not ready."},
        )

    result = remove_from_watchlist(ticker_normalized)
    if not result["removed"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Ticker not found in watchlist."},
        )

    if _market_source is not None:
        await _market_source.remove_ticker(ticker_normalized)

    return {"ticker": ticker_normalized, "removed": True}


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@app.get("/api/portfolio", tags=["portfolio"])
async def get_portfolio() -> dict:
    """Return current cash balance, positions with live prices, and total value."""
    try:
        from app.db.portfolio import get_portfolio as _get_portfolio
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Portfolio service not ready."},
        )

    if price_cache is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Price cache not ready.")

    try:
        return _get_portfolio("default", price_cache)
    except Exception as exc:
        logger.error("get_portfolio failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Portfolio service not ready."},
        )


@app.post("/api/portfolio/trade", status_code=status.HTTP_200_OK, tags=["portfolio"])
async def execute_trade_endpoint(body: dict) -> dict:
    """Execute a market order (buy or sell).

    Body: ``{"ticker": "aapl", "side": "buy", "quantity": 1.25}``
    """
    ticker_raw = body.get("ticker")
    side = body.get("side")
    quantity_raw = body.get("quantity")

    if not ticker_raw or not isinstance(ticker_raw, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TICKER", "message": "A valid ticker is required."},
        )
    ticker = ticker_raw.strip().upper()

    if side not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SIDE", "message": "Side must be 'buy' or 'sell'."},
        )

    try:
        quantity = float(quantity_raw)
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_QUANTITY", "message": "Quantity must be a positive number."},
        )

    if price_cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PRICE_UNAVAILABLE", "message": "Price data is not available."},
        )

    pu = price_cache.get(ticker)
    if pu is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PRICE_UNAVAILABLE", "message": f"No price available for '{ticker}'."},
        )

    price = pu.price

    try:
        from app.db.portfolio import execute_trade as _execute_trade
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Portfolio service not ready."},
        )

    result = _execute_trade("default", ticker, side, quantity, price, price_cache)

    if "error" in result:
        err = result["error"]
        code = err.get("code", "UNKNOWN_ERROR")
        http_code = {
            "INSUFFICIENT_CASH": status.HTTP_409_CONFLICT,
            "INSUFFICIENT_SHARES": status.HTTP_409_CONFLICT,
            "INVALID_TICKER": status.HTTP_400_BAD_REQUEST,
            "INVALID_SIDE": status.HTTP_400_BAD_REQUEST,
            "INVALID_QUANTITY": status.HTTP_400_BAD_REQUEST,
            "INVALID_PRICE": status.HTTP_400_BAD_REQUEST,
        }.get(code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=http_code, detail=err)

    # Record a snapshot immediately after each trade
    _record_snapshot(price_cache)

    return result


@app.get("/api/portfolio/history", tags=["portfolio"])
async def get_portfolio_history() -> dict:
    """Return portfolio value snapshots ordered by time."""
    try:
        from app.db import get_snapshots
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "Portfolio service not ready."},
        )

    from app.db import DEFAULT_USER_ID
    snapshots = get_snapshots(DEFAULT_USER_ID)
    return {"items": [{"total_value": s["total_value"], "recorded_at": s["recorded_at"]} for s in snapshots]}


# ===========================================================================
# LLM router dependency wiring
# ===========================================================================

async def _llm_portfolio_loader(user_id: str) -> dict:
    """Load portfolio context for the LLM router.

    Returns dict with cash_balance, positions, watchlist (list of dicts with
    ticker/price fields for the LLM client), and total_value.
    """
    from app.db import get_watchlist as _get_watchlist
    from app.db.portfolio import get_portfolio as _get_portfolio

    if price_cache is None:
        return {
            "cash_balance": 0.0,
            "positions": [],
            "watchlist": [],
            "total_value": 0.0,
        }

    portfolio = _get_portfolio("default", price_cache)

    # Build watchlist with live prices (LLM client expects list[dict])
    raw_watchlist = _get_watchlist(user_id)
    watchlist_with_prices = []
    for item in raw_watchlist:
        ticker = item["ticker"]
        pu = price_cache.get(ticker)
        watchlist_with_prices.append({
            "ticker": ticker,
            "price": pu.price if pu else None,
        })

    return {
        "cash_balance": portfolio["cash_balance"],
        "positions": portfolio["positions"],
        "watchlist": watchlist_with_prices,
        "total_value": portfolio["total_value"],
    }


async def _llm_trade_executor(user_id: str, ticker: str, side: str, quantity: float) -> dict:
    """Execute a trade on behalf of the LLM router."""
    from app.db.portfolio import execute_trade as _execute_trade
    if price_cache is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Price cache not ready.")
    pu = price_cache.get(ticker)
    if pu is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No price for '{ticker}'.")
    result = _execute_trade(user_id, ticker, side, quantity, pu.price, price_cache)
    if "error" in result:
        err = result["error"]
        code = err.get("code", "UNKNOWN_ERROR")
        http_code = {
            "INSUFFICIENT_CASH": status.HTTP_409_CONFLICT,
            "INSUFFICIENT_SHARES": status.HTTP_409_CONFLICT,
        }.get(code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=http_code, detail=err)
    return result


async def _llm_watchlist_adder(user_id: str, ticker: str) -> None:
    """Add a ticker to the watchlist on behalf of the LLM router."""
    from app.db import add_to_watchlist
    result = add_to_watchlist(ticker)
    if not result["added"]:
        code = result.get("error", "UNKNOWN")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": _code_to_message(code)},
        )
    if _market_source is not None:
        await _market_source.add_ticker(ticker)


async def _llm_watchlist_remover(user_id: str, ticker: str) -> None:
    """Remove a ticker from the watchlist on behalf of the LLM router."""
    from app.db import remove_from_watchlist
    result = remove_from_watchlist(ticker)
    if not result["removed"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not in watchlist.")


async def _llm_chat_saver(user_id: str, role: str, content: str, actions: str | None) -> None:
    """Save a chat message on behalf of the LLM router."""
    from app.db import add_message
    add_message(user_id, role, content, actions)


async def _llm_chat_loader(user_id: str, limit: int = 20) -> list[dict]:
    """Load chat messages on behalf of the LLM router."""
    from app.db import get_messages
    return get_messages(user_id, limit=limit)


def _configure_llm_router() -> None:
    """Wire up the LLM chat router's external dependencies."""
    try:
        from app.llm.router import configure
        configure(
            portfolio_loader=_llm_portfolio_loader,
            trade_executor=_llm_trade_executor,
            watchlist_adder=_llm_watchlist_adder,
            watchlist_remover=_llm_watchlist_remover,
            chat_saver=_llm_chat_saver,
            chat_loader=_llm_chat_loader,
        )
        logger.info("LLM chat router configured.")
    except ImportError:
        logger.warning("app.llm not available — chat endpoint will return 503.")


# ---------------------------------------------------------------------------
# Static file serving (Next.js build)
# ---------------------------------------------------------------------------

_static_mounted = False


def _mount_static():
    """Mount the Next.js static build at the root path if available."""
    global _static_mounted
    if _static_mounted:
        return
    candidates = ["static", "../static", "../../static"]
    for path in candidates:
        if os.path.isdir(path):
            app.mount("/", StaticFiles(directory=path, html=True), name="static")
            _static_mounted = True
            logger.info("Static files mounted from: %s", path)
            return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _code_to_message(code: str | None) -> str:
    """Translate a DB-layer error code to a human-readable message."""
    messages = {
        "WATCHLIST_FULL": "Watchlist limit of 30 tickers reached.",
        "ALREADY_EXISTS": "This ticker is already in your watchlist.",
        "NOT_FOUND": "The requested resource was not found.",
    }
    return (messages.get(code) or "An error occurred.") if code else "An error occurred."
