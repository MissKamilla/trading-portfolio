# Market Data Interface — Unified API

## Purpose

All market data — whether from the built-in simulator or the Massive REST API — flows through a single, source-agnostic interface defined by `MarketDataSource`. Downstream code (SSE streaming, portfolio valuation, trade execution) never imports a specific source; it reads from `PriceCache` and talks to `MarketDataSource` only through its abstract interface.

---

## Core Abstraction: `MarketDataSource`

```python
from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    def get_tickers(self) -> list[str]: ...
```

### Lifecycle

```
create_market_data_source(cache)   ← factory selects source by env var
source.start(["AAPL", "GOOGL", ...])   ← background task begins
  ... app runs ...
source.add_ticker("TSLA")          ← starts tracking new ticker
source.remove_ticker("GOOGL")       ← stops tracking ticker
  ... app shutting down ...
source.stop()                       ← cleanup; stops background task
```

---

## Data Model: `PriceUpdate`

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float  # Unix seconds

    @property
    def change(self) -> float: ...

    @property
    def change_percent(self) -> float: ...

    @property
    def direction(self) -> Literal["up", "down", "flat"]: ...

    def to_dict(self) -> dict: ...
```

`PriceUpdate` is the single data unit produced by both sources. It is **immutable** (`frozen=True`) and **slots-based** (`slots=True`) for memory efficiency — a `PriceUpdate` is created on every price tick and held briefly in the cache.

---

## Thread-Safe Cache: `PriceCache`

The `PriceCache` is the **single source of truth** for current prices. All producers write to it; all consumers read from it.

```python
class PriceCache:
    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price. Computes direction/change from the previous price."""

    def get(self, ticker: str) -> PriceUpdate | None: ...

    def get_all(self) -> dict[str, PriceUpdate]: ...

    def get_price(self, ticker: str) -> float | None: ...

    def remove(self, ticker: str) -> None: ...

    @property
    def version(self) -> int:
        """Monotonically increasing counter. Increments on every update.
        Used by SSE to detect whether anything changed since the last push."""
```

Thread safety is achieved with a `threading.Lock` around all read and write operations. The version counter enables the SSE endpoint to skip redundant pushes — if `cache.version` hasn't changed, the data hasn't changed.

### Cache Semantics

- `update()` rounds `price` and `previous_price` to cents before storing the `PriceUpdate`.
- On the first update for a ticker, `previous_price == price`, so `change == 0` and `direction == "flat"`.
- `get_all()` returns a shallow copy of the current cache, which protects internal state from accidental mutation by callers.
- `version` is read under the same lock as writes. This keeps the class consistent if the runtime or deployment model changes.
- The cache stores only the latest price per ticker. It does not keep historical bars or tick history.

---

## Factory: `create_market_data_source`

```python
from app.market import PriceCache, create_market_data_source

cache = PriceCache()
source = create_market_data_source(cache)
# Returns SimulatorDataSource if MASSIVE_API_KEY is unset or empty
# Returns MassiveDataSource if MASSIVE_API_KEY is set and non-empty
```

**Environment variables:**

| Variable | Effect |
|---|---|
| `MASSIVE_API_KEY` unset or empty | `SimulatorDataSource` (default, no API key needed) |
| `MASSIVE_API_KEY` set | `MassiveDataSource` (real market data) |

---

## Concrete Implementations

### SimulatorDataSource

- Default when no API key is provided
- Runs a background asyncio task that steps the GBM simulator every 500ms
- Writes results to `PriceCache`
- No external dependencies or API calls
- Produces correlated, realistic price movements with random shock events

### MassiveDataSource

- Active when `MASSIVE_API_KEY` is set
- Runs a background asyncio task that polls the Massive REST API at a configurable interval (default: 15s)
- Single batched request per poll cycle to minimize rate-limit usage
- Writes results to `PriceCache`
- Gracefully handles missing `last_trade` data per ticker

---

## SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)
# Returns FastAPI APIRouter with GET /api/stream/prices
```

The SSE endpoint pushes all prices every ~500ms **only when the cache version has changed** — eliminating redundant pushes when prices are stale.

```python
async def _generate_events(price_cache: PriceCache, ...) -> AsyncGenerator[str, None]:
    yield "retry: 1000\n\n"  # Browser reconnect after 1s

    last_version = -1
    while True:
        current_version = price_cache.version
        if current_version != last_version:
            last_version = current_version
            prices = price_cache.get_all()
            payload = json.dumps({t: u.to_dict() for t, u in prices.items()})
            yield f"data: {payload}\n\n"
        await asyncio.sleep(0.5)
```

`create_stream_router()` returns a fresh `APIRouter` per call. This avoids a module-level router accumulating duplicate routes in tests or repeated app factories.

---

## Usage from Application Code

```python
from app.market import PriceCache, create_market_data_source, create_stream_router

# === Startup ===
cache = PriceCache()
source = create_market_data_source(cache)

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
                   "NVDA", "META", "JPM", "V", "NFLX"]

await source.start(DEFAULT_TICKERS)

# Mount SSE router
router = create_stream_router(cache)
app.include_router(router)

# === During request handlers ===

# Get current price for trade
price = cache.get_price("AAPL")  # float | None

# Get all prices for watchlist endpoint
all_prices = cache.get_all()

# Dynamic watchlist management
await source.add_ticker("AMD")
await source.remove_ticker("NFLX")

# === On shutdown ===
await source.stop()
```

---

## Watchlist vs. Priced Ticker Set

The backend prices every ticker in:

```
watchlist tickers  ∪  open position tickers
```

This means:
- Removing a ticker from the watchlist does **not** stop pricing it if the user holds a position
- Portfolio valuation remains correct even for tickers not in the active watchlist
- `PriceCache.remove(ticker)` is called explicitly from `MarketDataSource.remove_ticker()` only when the user has no open position

At the market layer, `remove_ticker()` removes the ticker from both the active source and the cache. The application service that owns watchlists and positions should decide whether it is safe to call `remove_ticker()` in the first place.

---

## File Structure

```
backend/
  app/
    market/
      __init__.py          # public re-exports for app.market
      models.py            # PriceUpdate dataclass
      cache.py             # PriceCache
      interface.py         # MarketDataSource ABC
      seed_prices.py       # simulator constants and correlation groups
      simulator.py         # GBMSimulator + SimulatorDataSource
      massive_client.py    # MassiveDataSource
      factory.py           # create_market_data_source()
      stream.py            # create_stream_router() and SSE generator
```

The rest of the backend should import from `app.market` or the factory/router entry points, not from simulator or Massive internals.

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| Empty ticker list | Source starts, but no prices are written until tickers are added |
| Duplicate add | No duplicate tracking; source keeps one active ticker entry |
| Unknown simulator ticker | Starts from a random seed price between `$50` and `$300` and uses default GBM params |
| Missing Massive `last_trade` | Snapshot is skipped; last cached price remains |
| Massive poll failure | Error is logged; next poll retries; cache keeps previous values |
| SSE client disconnect | Generator exits after `request.is_disconnected()` |
| App shutdown | `source.stop()` cancels background task and releases source resources |

---

## Design Rationale

| Decision | Rationale |
|---|---|
| Strategy pattern for sources | Swap simulator ↔ real API without touching downstream code |
| PriceCache as single source of truth | Eliminates coordination between SSE, portfolio, and trade logic |
| Thread-safe cache | FastAPI runs on a single event loop but multiple threads may access prices during startup/shutdown |
| Immutable PriceUpdate | Prevents accidental mutation; safe to pass across async tasks |
| Version counter for SSE | Push optimization — skip sends when nothing changed |
| Batched Massive poll | Minimizes rate-limit usage; 4 req/min keeps within free tier |
| Router factory | Lets app startup inject the cache without globals and avoids duplicate test routes |
