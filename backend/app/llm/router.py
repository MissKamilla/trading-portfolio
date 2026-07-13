"""FastAPI router for the FinAlly chat endpoint.

Exposes POST /api/chat which:
  1. Loads portfolio context (cash, positions, watchlist, total value)
  2. Loads the last 20 chat messages for conversation history
  3. Calls the LLM client
  4. Auto-executes any trades / watchlist changes requested by the LLM
  5. Stores the exchange in chat_messages
  6. Returns the complete ChatResponse JSON
"""

from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .client import ChatClient
from .prompt import build_system_prompt
from .schema import ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# App-level dependencies  (set by the main application bootstrap)
# ---------------------------------------------------------------------------

_portfolio_loader: Any = None  # async fn: (user_id) -> dict
_trade_executor: Any = None   # async fn: (user_id, ticker, side, quantity) -> dict | raises
_watchlist_adder: Any = None  # async fn: (user_id, ticker) -> None | raises
_watchlist_remover: Any = None  # async fn: (user_id, ticker) -> None | raises
_chat_saver: Any = None       # async fn: (user_id, role, content, actions) -> None
_chat_loader: Any = None      # async fn: (user_id, limit=20) -> list[dict]


def configure(
    portfolio_loader,    # (user_id) -> {cash_balance, positions, watchlist, total_value}
    trade_executor,      # (user_id, ticker, side, quantity) -> trade dict
    watchlist_adder,     # (user_id, ticker) -> None
    watchlist_remover,   # (user_id, ticker) -> None
    chat_saver,          # (user_id, role, content, actions_json) -> None
    chat_loader,         # (user_id, limit) -> list[dict]
) -> None:
    """Wire up the external DB-facing functions. Call once at app startup."""
    global _portfolio_loader, _trade_executor, _watchlist_adder, _watchlist_remover, _chat_saver, _chat_loader
    _portfolio_loader = portfolio_loader
    _trade_executor = trade_executor
    _watchlist_adder = watchlist_adder
    _watchlist_remover = watchlist_remover
    _chat_saver = chat_saver
    _chat_loader = chat_loader


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Dependency injection helpers
# ---------------------------------------------------------------------------

def _get_client() -> ChatClient:
    return ChatClient(system_prompt_fn=build_system_prompt)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    client: Annotated[ChatClient, Depends(_get_client)],
) -> ChatResponse:
    """Receive a user message, call the LLM, execute any requested actions,
    persist the exchange, and return the structured response."""
    user_id = "default"

    if not req.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_MESSAGE", "message": "Message cannot be empty."},
        )

    # 1. Load portfolio context
    try:
        ctx = await _portfolio_loader(user_id)
    except Exception as exc:
        logger.error("Failed to load portfolio for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PORTFOLIO_UNAVAILABLE",
                "message": "Portfolio data temporarily unavailable.",
            },
        ) from exc

    cash_balance: float = ctx["cash_balance"]
    positions: list[dict] = ctx["positions"]
    watchlist: list[dict] = ctx["watchlist"]
    total_value: float = ctx["total_value"]

    # 2. Load conversation history (last 20 turns)
    history: list[dict] = await _chat_loader(user_id, limit=20)

    # 3. Call LLM
    current_time = _now_iso()
    llm_response: ChatResponse = await client.chat(
        message=req.message,
        cash_balance=cash_balance,
        positions=positions,
        watchlist=watchlist,
        total_value=total_value,
        conversation_history=history,
        current_time=current_time,
    )

    # 4. Execute requested trades (best-effort; errors captured in response)
    executed_trades: list[dict] = []
    for trade in llm_response.trades:
        trade_dict: dict[str, Any] = {
            "ticker": trade.ticker,
            "side": trade.side,
            "quantity": trade.quantity,
            "status": trade.status,
            "error": trade.error.model_dump() if trade.error else None,
        }
        if trade.status == "executed":
            try:
                result: dict[str, Any] = await _trade_executor(
                    user_id=user_id,
                    ticker=trade.ticker,
                    side=trade.side,
                    quantity=trade.quantity,
                )
                trade_dict.update(result)
            except Exception as exc:
                logger.warning("LLM-triggered trade failed: %s", exc)
                trade_dict["status"] = "failed"
                trade_dict["error"] = {"code": "EXECUTION_ERROR", "message": str(exc)}
        executed_trades.append(trade_dict)

    # 5. Execute requested watchlist changes
    executed_watchlist: list[dict] = []
    for wc in llm_response.watchlist_changes:
        wc_dict: dict[str, Any] = {
            "action": wc.action,
            "ticker": wc.ticker,
            "status": wc.status,
            "error": wc.error.model_dump() if wc.error else None,
        }
        if wc.status == "executed":
            try:
                if wc.action == "add":
                    await _watchlist_adder(user_id, wc.ticker)
                elif wc.action == "remove":
                    await _watchlist_remover(user_id, wc.ticker)
            except Exception as exc:
                logger.warning("LLM-triggered watchlist change failed: %s", exc)
                wc_dict["status"] = "failed"
                wc_dict["error"] = {"code": "EXECUTION_ERROR", "message": str(exc)}
        executed_watchlist.append(wc_dict)

    # 6. Persist the exchange to chat_messages
    try:
        actions_json = {
            "trades": executed_trades,
            "watchlist_changes": executed_watchlist,
        }
        await _chat_saver(
            user_id=user_id,
            role="user",
            content=req.message,
            actions=_json.dumps(actions_json),
        )
        await _chat_saver(
            user_id=user_id,
            role="assistant",
            content=llm_response.message,
            actions=_json.dumps(actions_json),
        )
    except Exception as exc:
        # Non-fatal: log and continue — the response has already been built
        logger.error("Failed to persist chat messages: %s", exc)

    # 7. Return response (actions reflect actual execution status)
    return ChatResponse(
        message=llm_response.message,
        trades=executed_trades,
        watchlist_changes=executed_watchlist,
    )
