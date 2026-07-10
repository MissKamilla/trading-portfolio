# Market Data Design — Adapted for FinAlly

This document is the implementation-level map for the current FinAlly market data subsystem. It keeps the teacher's overall structure, but adapts it to the code that exists in this project now.

Everything covered here lives under `backend/app/market/`.

---

## Goals

- Provide one market data interface for simulated and real prices.
- Keep downstream code source-agnostic: SSE, portfolio valuation, and trade execution read from `PriceCache`.
- Work without external services by default through the GBM simulator.
- Use Massive REST polling only when `MASSIVE_API_KEY` is configured.
- Stay within the Massive free tier by batching tickers and polling at 15 seconds.
- Keep the live UI responsive by streaming only when cached prices change.

---

## Module Structure

```
backend/
  app/
    market/
      __init__.py          # public re-exports
      models.py            # PriceUpdate
      cache.py             # PriceCache
      interface.py         # MarketDataSource
      seed_prices.py       # simulator constants
      simulator.py         # GBMSimulator + SimulatorDataSource
      massive_client.py    # MassiveDataSource
      factory.py           # source selection by env var
      stream.py            # FastAPI SSE router factory
```

Public application code should use:

```python
from app.market import PriceCache, create_market_data_source
from app.market.stream import create_stream_router
```

Direct imports from `simulator.py` or `massive_client.py` should stay limited to tests and market-layer internals.

---

## Data Flow

```
SimulatorDataSource OR MassiveDataSource
  -> PriceCache.update(...)
      -> SSE /api/stream/prices
      -> portfolio valuation
      -> trade execution
```

`PriceCache` is the boundary between producers and consumers. Data sources push updates into the cache on their own schedule. Consumers do not care whether the current price came from the simulator or Massive.

---

## Price Model

`PriceUpdate` is immutable and slots-based:

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float

    @property
    def change(self) -> float: ...

    @property
    def change_percent(self) -> float: ...

    @property
    def direction(self) -> str: ...

    def to_dict(self) -> dict: ...
```

`change`, `change_percent`, and `direction` are computed properties. They are not stored separately, which prevents stale derived values.

Current scope is "latest tradable price". The model intentionally does not include bid/ask, volume, OHLC, previous close, or historical bars yet.

---

## PriceCache

`PriceCache` stores the latest `PriceUpdate` per ticker.

Important behavior:

- All reads and writes use `threading.Lock`.
- `update()` increments a monotonically increasing `version`.
- `get_all()` returns a shallow copy.
- `get_price()` is the convenience method for trade execution.
- `remove()` drops a ticker from the cache.
- `version` is used by SSE to skip duplicate payloads.

The cache is not a database and does not keep history. If charts need historical data, add a separate bar store or chart service instead of expanding `PriceCache` into a mixed responsibility object.

---

## MarketDataSource Interface

Both data sources implement the same lifecycle:

```python
class MarketDataSource(ABC):
    async def start(self, tickers: list[str]) -> None: ...
    async def stop(self) -> None: ...
    async def add_ticker(self, ticker: str) -> None: ...
    async def remove_ticker(self, ticker: str) -> None: ...
    def get_tickers(self) -> list[str]: ...
```

The interface does not return prices. Sources own update timing and write to `PriceCache`.

---

## Simulator Source

Default source when `MASSIVE_API_KEY` is unset.

Components:

- `GBMSimulator`: pure math engine, no async, no I/O.
- `SimulatorDataSource`: async wrapper that calls `step()` every 500ms and writes to `PriceCache`.

The simulator uses:

- Geometric Brownian Motion.
- Per-ticker drift and volatility.
- Cholesky decomposition for correlated moves.
- Random 2-5% shock events with low probability.
- Immediate cache seeding on startup and ticker add.

This is sufficient for a trading workstation demo, portfolio valuation, and frontend streaming. It is not intended for quantitative backtesting.

---

## Massive Source

Active only when `MASSIVE_API_KEY` is non-empty.

Behavior:

- Creates one `RESTClient` on `start()`.
- Performs one immediate poll so the cache gets data right away.
- Uses `get_snapshot_all(SnapshotMarketType.STOCKS, tickers=...)`.
- Runs the synchronous SDK call inside `asyncio.to_thread()`.
- Polls every 15 seconds by default, which is 4 requests/minute.
- Skips malformed snapshots or tickers without `last_trade`.
- Logs poll failures and retries on the next interval.

Current extracted fields:

- ticker
- last trade price
- last trade timestamp, converted from milliseconds to Unix seconds

Future fields like previous close, bid/ask, volume, and OHLC should be added through a richer quote model, not forced into `PriceUpdate`.

---

## Source Factory

`create_market_data_source(price_cache)` selects the source:

| Environment | Source |
|---|---|
| `MASSIVE_API_KEY` unset or empty | `SimulatorDataSource` |
| `MASSIVE_API_KEY` set | `MassiveDataSource` |

The returned source is unstarted. App startup must call `await source.start(initial_tickers)`.

---

## SSE Streaming

`create_stream_router(price_cache)` creates a FastAPI router with:

```
GET /api/stream/prices
```

The stream:

- sends `retry: 1000` for browser reconnects;
- checks `request.is_disconnected()`;
- compares `price_cache.version` to the last sent version;
- serializes all current prices only when the version changes;
- sets `X-Accel-Buffering: no` for reverse proxies.

The router is created inside the factory call, not as a mutable module-level singleton.

---

## FastAPI Lifecycle

Expected startup flow:

```python
price_cache = PriceCache()
market_source = create_market_data_source(price_cache)
await market_source.start(DEFAULT_TICKERS)
app.include_router(create_stream_router(price_cache))
```

Expected shutdown flow:

```python
await market_source.stop()
```

The app should keep references to both `price_cache` and `market_source`, usually on `app.state` or through the existing dependency pattern.

---

## Watchlist Coordination

The market layer only knows which tickers are actively tracked. It does not know why a ticker is tracked.

Application-level services should track:

```
priced tickers = watchlist tickers ∪ open position tickers
```

Only call `source.remove_ticker(ticker)` when the ticker is absent from both the watchlist and open positions. Otherwise portfolio valuation can lose its current price.

---

## Configuration

| Setting | Default | Notes |
|---|---:|---|
| `MASSIVE_API_KEY` | empty | Empty means simulator mode |
| Simulator interval | 0.5s | Two ticks per second |
| Simulator event probability | 0.001 | Per ticker per tick |
| Massive poll interval | 15s | 4 requests/minute |
| SSE interval | 0.5s | Sends only when cache version changes |

Paid Massive tiers can use 2-5 second REST polling. Sub-second real market data should use WebSockets instead.

---

## Tests to Maintain

- `PriceUpdate` computed fields and `to_dict()`.
- `PriceCache` update/get/remove/version behavior.
- `PriceCache` concurrent writes.
- Factory source selection with and without `MASSIVE_API_KEY`.
- Simulator deterministic behavior with seeded NumPy RNG.
- Simulator full default ticker set Cholesky rebuild.
- Simulator source startup seeding, add/remove, and cancellation.
- Massive poll parsing, timestamp conversion, malformed snapshot skip, and failure retry.
- SSE emits initial retry directive and only sends changed versions.

---

## Known Boundaries

- No historical price store.
- No bid/ask or spread-aware execution.
- No market calendar awareness.
- No previous-day close seeding yet.
- No WebSocket integration.
- No multi-asset support beyond stock tickers.

These are acceptable boundaries for the current project. They should become explicit feature work only when the frontend or trading logic needs them.

---

## Future Enhancements

1. Seed real-data `previous_price` from Massive previous close on startup.
2. Add a separate quote/detail model for bid/ask, day OHLC, volume, and previous close.
3. Add historical aggregate fetching for chart views.
4. Add market-hours awareness so the UI can show stale/closed-market states.
5. Add WebSocket source for paid Massive plans.
6. Store short rolling price history if the frontend needs sparklines without a separate chart API.
