# Massive API — Real Market Data

> **Note:** Polygon.io has been rebranded to **Massive**. The underlying API is the same; the Python package is `massive`, the domain is `massive.com`. This document uses the current Massive branding.

---

## Overview

Massive provides REST and WebSocket APIs for real-time and historical stock market data. FinAlly uses the **REST API only**, polling at a configurable interval and writing results into the shared `PriceCache`.

### Why REST over WebSocket?

- Simpler integration — no persistent connection management
- Works on the free tier (5 req/min) without WebSocket complexity
- One endpoint can return prices for many tickers simultaneously
- Sufficient for a simulated trading workstation where sub-second precision is not required

### Free Tier Limits

| Limit | Value |
|---|---|
| REST requests | 5 per minute |
| WebSocket connections | 1 concurrent |
| Tickers per snapshot | Unlimited (batched) |
| Historical data | Limited to 1 year back |

Paid tiers remove rate limits and add intraday aggregate endpoints.

---

## API Authentication

All requests require an API key passed as a header:

```
Authorization: Bearer YOUR_API_KEY
```

The key is set via the `MASSIVE_API_KEY` environment variable. The backend initializes the client once on startup:

```python
from massive import RESTClient

client = RESTClient(api_key=os.environ["MASSIVE_API_KEY"])
```

The SDK can also read `MASSIVE_API_KEY` from the environment automatically:

```python
client = RESTClient()
```

Base URL (used internally by the SDK):
```
https://api.massive.com/v3
```

---

## Core Endpoints

### 1. Snapshot — All Tickers

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

Returns a snapshot of all US stock tickers in a single response. This is the primary endpoint used by FinAlly's `MassiveDataSource`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `tickers` | `list[str]` | List of ticker symbols to include |

**Response shape:**

```json
{
  "tickers": [
    {
      "ticker": "AAPL",
      "last_trade": {
        "price": 190.42,
        "timestamp": 1719936000000
      },
      "last_quote": {
        "bid_price": 190.40,
        "ask_price": 190.44,
        "timestamp": 1719936000000
      },
      "day": {
        "open": 189.10,
        "high": 191.00,
        "low": 188.90,
        "close": 190.42,
        "volume": 52341200
      },
      "last_updated": 1719936000000
    }
  ]
}
```

**Important fields for FinAlly:**

| Field | Path | Usage |
|---|---|---|
| `price` | `last_trade.price` | Current price → `PriceUpdate.price` |
| `timestamp` | `last_trade.timestamp` | Milliseconds → divide by 1000 for Unix seconds |

If a ticker has no recent trade, `last_trade` may be `null`. The client skips such tickers with a warning.

---

### 2. Snapshot — Single Ticker

```
GET /v2/snapshot/locale/us/markets/stocks/{ticker}
```

Returns a snapshot for a single ticker. Useful for checking price for a specific trade before execution.

**Response shape** (same as above, but single object):

```json
{
  "ticker": "AAPL",
  "last_trade": {
    "price": 190.42,
    "timestamp": 1719936000000
  },
  "last_quote": { ... },
  "day": { ... },
  "last_updated": 1719936000000
}
```

---

### 3. Previous Close

```
GET /v2/aggs/ticker/{ticker}/prev
```

Returns the previous day's OHLCV bar. Useful for computing the prior-day close price (needed for `previous_price` in `PriceUpdate`).

**Response shape:**

```json
{
  "ticker": "AAPL",
  "adjusted_close": 189.75,
  "results": [
    {
      "o": 188.00,
      "h": 191.50,
      "l": 187.50,
      "c": 189.75,
      "v": 52431000,
      "t": 1719849600000
    }
  ]
}
```

---

### 4. Aggregates (OHLCV Bars)

```
GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}
```

Returns OHLCV bars at a specified resolution.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `from` | ISO date | Start date (e.g., `2024-01-01`) |
| `to` | ISO date | End date (e.g., `2024-01-31`) |
| `multiplier` | int | Number of `timespan` units (e.g., `1`, `5`, `15`) |
| `timespan` | str | One of: `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year` |

**Example:** 5-minute bars for January 2024:
```
GET /v2/aggs/ticker/AAPL/range/5/minute?from=2024-01-01&to=2024-01-31
```

**Response shape:**

```json
{
  "ticker": "AAPL",
  "results": [
    {
      "o": 189.00,
      "h": 189.90,
      "l": 188.80,
      "c": 189.50,
      "v": 124500,
      "t": 1719936000000,
      "n": 1823
    }
  ]
}
```

This endpoint is not used by FinAlly's current polling architecture but is documented for future chart features.

---

### 5. Last Trade

```
GET /v2/last/trade/{ticker}
```

Returns the most recent trade for a ticker.

```json
{
  "status": "OK",
  "request_id": "abc123",
  "results": {
    "t": 1719936000000,
    "p": 190.42,
    "s": 100,
    "c": ["RT", "LE"],
    "i": 12345,
    "x": 4
  }
}
```

| Field | Meaning |
|---|---|
| `p` | Trade price |
| `s` | Trade size (shares) |
| `t` | Timestamp (ms) |
| `c` | Condition codes |

---

### 6. Last Quote

```
GET /v2/last/quote/{ticker}
```

Returns the most recent NBBO quote (best bid/ask).

```json
{
  "status": "OK",
  "results": {
    "t": 1719936000000,
    "bp": 190.40,
    "ap": 190.44,
    "bs": 300,
    "as": 200
  }
}
```

| Field | Meaning |
|---|---|
| `bp` | Bid price |
| `ap` | Ask price |
| `bs` | Bid size |
| `as` | Ask size |

---

## Rate Limit Handling

Massive enforces rate limits per API key:

- **Free tier:** 5 requests per minute across all endpoints
- **Higher tiers:** Higher limits; consult your Massive dashboard

### FinAlly's Rate Limit Strategy

The `MassiveDataSource` uses a **single batch endpoint** (`get_snapshot_all`) per poll cycle. This minimizes request count:

```
Requests per minute = 60 / poll_interval_seconds
```

| Poll interval | Requests/min | Free tier OK? |
|---|---|---|
| 15s | 4 | Yes |
| 12s | 5 | At limit |
| 5s | 12 | No (paid tier) |
| 2s | 30 | No (paid tier) |

**Default poll interval: 15 seconds.** This keeps the free-tier request count at 4/min, leaving headroom for occasional health checks or trade-validation lookups.

For paid tiers, a 2-5 second interval is reasonable for this project. Sub-second updates should use WebSocket streaming instead of REST polling.

### Retry Logic

If a poll fails (429, 5xx, network error), the loop logs the error and retries on the next interval. It does not crash or retry immediately — that would amplify the problem under rate limiting.

```python
try:
    snapshots = await asyncio.to_thread(self._fetch_snapshots)
    for snap in snapshots:
        self._cache.update(ticker=snap.ticker, price=snap.last_trade.price, ...)
except Exception as e:
    logger.error("Massive poll failed: %s", e)
    # Retry on next interval; cache retains last known prices
```

---

## Error Codes

| HTTP Status | Code | Cause | FinAlly behavior |
|---|---|---|---|
| 401 | — | Invalid/missing API key | Logged as error; no retry |
| 403 | — | Insufficient permissions | Logged as error; no retry |
| 429 | — | Rate limit exceeded | Retry on next interval |
| 503 | — | Service temporarily unavailable | Retry on next interval |
| Various | — | Network error, timeout | Retry on next interval |

---

## Python SDK Usage

### Installation

```bash
pip install massive>=1.0.0
```

### Basic Usage

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient(api_key="your_api_key_here")  # or RESTClient() from MASSIVE_API_KEY

# Snapshot all watched tickers
snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT"],
)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.last_trade.price}")

# Previous close aggregate
prev = client.get_previous_close_agg(ticker="AAPL")
for bar in prev:
    print(f"Previous close: ${bar.close}")

# Single ticker snapshot
detail = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS,
    ticker="AAPL",
)
print(f"Current price: ${detail.last_trade.price}")
```

### Model Constants

```python
from massive.rest.models import SnapshotMarketType

SnapshotMarketType.STOCKS   # "STOCKS"
SnapshotMarketType.OPTIONS  # "OPTIONS"
SnapshotMarketType.CRYPTO   # "CRYPTO"
SnapshotMarketType.FX       # "FX"
```

---

## Integration with FinAlly

### Data Flow

```
Massive REST API (polling)
  → MassiveDataSource._fetch_snapshots()
      → asyncio.to_thread()  (sync SDK call in thread)
          → RESTClient.get_snapshot_all()
              → list of Snapshot objects
                  → for each: cache.update(ticker, price, timestamp)
                      → PriceCache (thread-safe, in-memory)
                          ├──→ SSE /api/stream/prices
                          ├──→ Portfolio valuation
                          └──→ Trade execution
```

### Key Design Decisions

1. **Thread-based SDK call:** The `massive` SDK is synchronous. Calling it directly would block the FastAPI event loop, so `asyncio.to_thread()` wraps it.
2. **Batched snapshot:** One API call per poll cycle, regardless of how many tickers are watched. The free tier allows 4-5 calls/min, which is sufficient.
3. **Graceful degradation:** If a ticker has no `last_trade`, it is skipped with a warning. Its price remains whatever the last poll recorded. The watchlist/position is **not** removed — that would break portfolio valuation for held positions.
4. **Previous close:** The current implementation uses the in-memory `previous_price` from the cache (i.e., the price from the prior tick, not the prior day's close). For future intraday charting, `GET /v2/aggs/ticker/{ticker}/prev` should be called once on startup to seed `previous_price` with the actual prior-day close.
5. **Market-hours behavior:** During closed hours, snapshots may reflect the last regular or extended-hours trade. The UI should treat timestamps as part of the data, not assume a fresh tick.

### Current Implementation Scope

The current `MassiveDataSource` extracts:

- `snap.ticker`
- `snap.last_trade.price`
- `snap.last_trade.timestamp / 1000.0`

It does **not** yet persist `day.previous_close`, bid/ask, day OHLC, volume, or historical bars. Those fields belong in a future richer quote model rather than in `PriceUpdate`, which intentionally stays small for SSE and trade pricing.

---

## Future Enhancements

- **Previous-day close seeding:** On `start()`, call `GET /v2/aggs/ticker/{ticker}/prev` for each ticker to set `previous_price` to the actual prior-day close instead of the first simulated/current tick's price.
- **WebSocket streaming:** For paid tiers, replace polling with a WebSocket connection for near-real-time updates (sub-500ms latency).
- **Intraday OHLCV:** Store `GET /v2/aggs/ticker/{ticker}/range/5/minute` results to support the frontend's detailed chart view.
- **Error classification:** Distinguish 429 (rate limit) from 5xx (server error) to implement exponential backoff on server errors only.
