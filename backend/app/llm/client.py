"""LLM client for FinAlly using LiteLLM via OpenRouter.

Falls back to deterministic mocks when:
  - LLM_MOCK=true
  - OPENROUTER_API_KEY is absent or empty
  - The request times out (30 s) or the provider returns an error
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import litellm

from .mock import build_mock_response
from .schema import ChatResponse

if TYPE_CHECKING:
    from .prompt import build_system_prompt

logger = logging.getLogger(__name__)

#: Default OpenRouter model — Cerebras inference via OpenRouter
DEFAULT_MODEL = "openrouter/openai/gpt-oss-120b"

#: Request timeout in seconds
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_mock_mode() -> bool:
    """Return True when mock mode should be active."""
    mock_flag = os.environ.get("LLM_MOCK", "").strip().lower()
    if mock_flag in ("true", "1", "yes"):
        return True
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        # No key → always mock
        return True
    return False


def _get_model() -> str:
    """Return the configured OpenRouter model string."""
    return os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


# ---------------------------------------------------------------------------
# ChatClient
# ---------------------------------------------------------------------------

class ChatClient:
    """Thin client that calls the LLM and returns structured ChatResponse objects.

    Parameters
    ----------
    system_prompt:
        A callable that accepts the context dict and returns the system prompt str.
        The context dict contains: cash_balance, positions, watchlist, total_value,
        conversation_history, current_time.
    """

    def __init__(
        self,
        system_prompt_fn: "build_system_prompt",
    ) -> None:
        self._system_prompt_fn = system_prompt_fn
        litellm.suppress_debug_info = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        message: str,
        *,
        cash_balance: float,
        positions: list[dict],
        watchlist: list[dict],
        total_value: float,
        conversation_history: list[dict],
        current_time: str,
    ) -> ChatResponse:
        """Send a chat message and return the structured assistant response.

        Falls back to mock automatically on any error.
        """
        if _is_mock_mode():
            return self._mock_reply(
                message=message,
                cash_balance=cash_balance,
                positions=positions,
                watchlist=watchlist,
                total_value=total_value,
                conversation_history=conversation_history,
            )

        context = {
            "cash_balance": cash_balance,
            "positions": positions,
            "watchlist": watchlist,
            "total_value": total_value,
            "conversation_history": conversation_history,
            "current_time": current_time,
        }

        system_prompt = self._system_prompt_fn(**context)
        model = _get_model()

        try:
            raw = await self._call_llm(
                model=model,
                system_prompt=system_prompt,
                user_message=message,
            )
            return self._parse_response(raw)
        except Exception as exc:  # pragma: no cover — real-LLM path only
            logger.warning("LLM call failed (%s), falling back to mock: %s", model, exc)
            return self._mock_reply(
                message=message,
                cash_balance=cash_balance,
                positions=positions,
                watchlist=watchlist,
                total_value=total_value,
                conversation_history=conversation_history,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str,
    ) -> ChatResponse:
        """Make the actual LiteLLM call with structured output."""
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},  # LiteLLM structured output hint
            timeout=REQUEST_TIMEOUT,
            temperature=0.4,
            max_tokens=1024,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty response content")

        return self._parse_response(content)

    @staticmethod
    def _parse_response(content: str) -> ChatResponse:
        """Parse the raw JSON string into a ChatResponse, validating the schema."""
        import json

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

        return ChatResponse(**data)

    @staticmethod
    def _mock_reply(
        message: str,
        cash_balance: float,
        positions: list[dict],
        watchlist: list[dict],
        total_value: float,
        conversation_history: list[dict],
    ) -> ChatResponse:
        """Delegate to the mock module with the current context."""
        # Extract just ticker prices from watchlist dicts
        price_map: dict[str, float] = {
            w["ticker"]: w["price"]
            for w in watchlist
            if w.get("price") is not None
        }
        return build_mock_response(
            user_message=message,
            cash_balance=cash_balance,
            prices=price_map,
            positions=positions,
            watchlist=[w["ticker"] for w in watchlist],
        )
