"""Tests for SSE market price streaming."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import APIRouter

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


class DummyRequest:
    """Minimal request object for exercising the SSE generator."""

    def __init__(self, disconnected: bool = False) -> None:
        self.client = SimpleNamespace(host="127.0.0.1")
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


@pytest.mark.asyncio
class TestPriceStream:
    """Unit tests for the SSE stream helpers."""

    async def test_generate_events_starts_with_retry_directive(self):
        """Test that the stream starts with browser reconnect configuration."""
        cache = PriceCache()
        request = DummyRequest()
        events = _generate_events(cache, request, interval=0.01)

        assert await anext(events) == "retry: 1000\n\n"
        await events.aclose()

    async def test_generate_events_serializes_cache_payload(self):
        """Test that changed cache data is emitted as an SSE data event."""
        cache = PriceCache()
        cache.update("AAPL", 190.50, timestamp=123.0)
        request = DummyRequest()
        events = _generate_events(cache, request, interval=0.01)

        await anext(events)
        event = await anext(events)

        assert event.startswith("data: ")
        assert event.endswith("\n\n")

        payload = json.loads(event.removeprefix("data: ").strip())
        assert payload["AAPL"]["ticker"] == "AAPL"
        assert payload["AAPL"]["price"] == 190.50
        assert payload["AAPL"]["direction"] == "flat"

        await events.aclose()

    async def test_generate_events_waits_for_next_cache_version(self):
        """Test that duplicate cache versions are not emitted again."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        request = DummyRequest()
        events = _generate_events(cache, request, interval=0.01)

        await anext(events)
        first_event = await anext(events)

        async def update_later() -> None:
            await asyncio.sleep(0.03)
            cache.update("AAPL", 191.00)

        task = asyncio.create_task(update_later())
        second_event = await asyncio.wait_for(anext(events), timeout=0.2)
        await task

        assert second_event != first_event
        payload = json.loads(second_event.removeprefix("data: ").strip())
        assert payload["AAPL"]["price"] == 191.00
        assert payload["AAPL"]["direction"] == "up"

        await events.aclose()

    async def test_generate_events_stops_after_disconnect(self):
        """Test that a disconnected client stops the generator."""
        cache = PriceCache()
        request = DummyRequest(disconnected=True)
        events = _generate_events(cache, request, interval=0.01)

        assert await anext(events) == "retry: 1000\n\n"
        with pytest.raises(StopAsyncIteration):
            await anext(events)

    async def test_create_stream_router_registers_prices_route(self):
        """Test that the router factory creates the expected route."""
        cache = PriceCache()
        router = create_stream_router(cache)

        assert isinstance(router, APIRouter)
        assert router.prefix == "/api/stream"
        assert any(route.path == "/api/stream/prices" for route in router.routes)
