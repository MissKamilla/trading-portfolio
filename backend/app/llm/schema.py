"""Pydantic models for structured LLM output in FinAlly chat."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Error information when an LLM-suggested action cannot be executed."""

    code: str = Field(description="Machine-readable error code, e.g. INSUFFICIENT_CASH")
    message: str = Field(description="Human-readable error description")


class TradeAction(BaseModel):
    """A single trade the LLM has requested to execute."""

    ticker: str = Field(description="Ticker symbol, e.g. AAPL")
    side: Literal["buy", "sell"] = Field(description="Buy or sell side")
    quantity: float = Field(description="Number of shares; fractional allowed")
    status: Literal["executed", "failed"] = Field(
        description="Whether the trade was executed or failed validation"
    )
    error: ErrorDetail | None = Field(
        default=None,
        description="Error details if status is 'failed', null otherwise",
    )


class WatchlistChange(BaseModel):
    """A single watchlist modification the LLM has requested."""

    action: Literal["add", "remove"] = Field(description="Add or remove the ticker")
    ticker: str = Field(description="Ticker symbol, e.g. AAPL")
    status: Literal["executed", "failed"] = Field(
        description="Whether the change was applied or rejected"
    )
    error: ErrorDetail | None = Field(
        default=None,
        description="Error details if status is 'failed', null otherwise",
    )


class ChatResponse(BaseModel):
    """Structured response from the FinAlly chat assistant.

    The LLM is instructed to return exactly this JSON shape.
    """

    message: str = Field(
        description="Conversational response to the user"
    )
    trades: list[TradeAction] = Field(
        default_factory=list,
        description="Trades the assistant has executed or attempted",
    )
    watchlist_changes: list[WatchlistChange] = Field(
        default_factory=list,
        description="Watchlist additions/removals the assistant has made",
    )
