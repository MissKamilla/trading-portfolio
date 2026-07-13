"""LLM integration for FinAlly.

Public API
----------
ChatClient  : Sends messages to the LLM and returns structured ChatResponse objects.
build_system_prompt : Builds the system prompt from portfolio context.
build_mock_response  : Deterministic mock response (used when LLM_MOCK=true).
ChatResponse, TradeAction, WatchlistChange, ErrorDetail : Pydantic models.
chat_router         : FastAPI router for POST /api/chat (wire into the main app).

Usage
-----
```python
from app.llm import chat_router
app.include_router(chat_router)
```
"""

from .client import ChatClient
from .mock import build_mock_response
from .prompt import build_system_prompt
from .router import router as chat_router
from .schema import (
    ChatResponse,
    ErrorDetail,
    TradeAction,
    WatchlistChange,
)

__all__ = [
    "ChatClient",
    "ChatResponse",
    "ErrorDetail",
    "TradeAction",
    "WatchlistChange",
    "build_mock_response",
    "build_system_prompt",
    "chat_router",
]
