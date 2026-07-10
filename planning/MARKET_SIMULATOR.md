# Market Simulator — Design & Implementation

## Overview

The `GBMSimulator` generates realistic synthetic stock prices using **Geometric Brownian Motion (GBM)** — the same stochastic process used in quantitative finance to model stock prices. It supports:

- Per-ticker drift (mu) and volatility (sigma) parameters
- Correlated price moves across tickers (Cholesky decomposition)
- Random shock events for visual drama
- Dynamic add/remove of tickers

The `SimulatorDataSource` wraps the simulator and exposes it as a `MarketDataSource`, writing prices to `PriceCache` on a fixed interval.

---

## Mathematical Model: Geometric Brownian Motion

GBM models the evolution of a stock price $S(t)$ as:

```
S(t + dt) = S(t) · exp((μ - σ²/2) · dt + σ · √dt · Z)
```

Where:

| Symbol | Meaning | Typical range |
|---|---|---|
| `μ` | Annual drift (expected return) | 0.03 – 0.08 |
| `σ` | Annual volatility | 0.15 – 0.50 |
| `dt` | Time step as fraction of a trading year | ~8.5e-8 (500ms) |
| `Z` | Standard normal random variable | N(0, 1) |

The drift term `(μ - σ²/2)` ensures the expected value of $S(t)$ grows at rate μ (Itô's lemma result).

### Time Step

One simulation step = 500ms. Expressed as a fraction of a trading year:

```
Trading seconds per year = 252 days × 6.5 hours/day × 3600 s/hour = 5,896,800
dt = 0.5s / 5,896,800 ≈ 8.48 × 10⁻⁸
```

This makes the simulated prices scale correctly to the annual σ and μ parameters.

---

## Correlation: Cholesky Decomposition

In reality, tech stocks tend to move together. The simulator models this with a **correlation matrix** decomposed via Cholesky factorization.

### Correlation Groups

```python
TECH_CORR = 0.6    # AAPL ↔ GOOGL, MSFT, AMZN, META, NVDA, NFLX
FINANCE_CORR = 0.5  # JPM ↔ V
CROSS_GROUP_CORR = 0.3  # tech ↔ finance
TSLA_CORR = 0.3    # TSLA is semi-independent (tech-adjacent but idiosyncratic)
```

### Cholesky Decomposition

Given an N×N correlation matrix C (symmetric, positive semi-definite), the Cholesky decomposition finds a lower-triangular matrix L such that:

```
C = L · Lᵀ
```

Then correlated normal variables are generated as:

```
Z_correlated = L · Z_independent
```

Where `Z_independent ~ N(0, 1)` for each ticker.

**Why this matters:** Without correlation, all tickers would drift independently and the portfolio would look like noise. With correlation, sector-wide moves appear naturally, making the simulator feel realistic.

**Rebuilding L:** The correlation matrix changes when tickers are added or removed (because the cross-section of tickers changes). `GBMSimulator._rebuild_cholesky()` is called on every `add_ticker` / `remove_ticker`.

### Correlation Matrix Structure

For 10 default tickers (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX):

```
           AAPL GOOGL MSFT AMZN TSLA NVDA META JPM  V   NFLX
AAPL        1.0  0.6  0.6  0.6  0.3  0.6  0.6  0.3 0.3  0.6
GOOGL       0.6  1.0  0.6  0.6  0.3  0.6  0.6  0.3 0.3  0.6
MSFT        0.6  0.6  1.0  0.6  0.3  0.6  0.6  0.3 0.3  0.6
AMZN        0.6  0.6  0.6  1.0  0.3  0.6  0.6  0.3 0.3  0.6
TSLA        0.3  0.3  0.3  0.3  1.0  0.3  0.3  0.3 0.3  0.3
NVDA        0.6  0.6  0.6  0.6  0.3  1.0  0.6  0.3 0.3  0.6
META        0.6  0.6  0.6  0.6  0.3  0.6  1.0  0.3 0.3  0.6
JPM         0.3  0.3  0.3  0.3  0.3  0.3  0.3  1.0 0.5  0.3
V           0.3  0.3  0.3  0.3  0.3  0.3  0.3  0.5 1.0  0.3
NFLX        0.6  0.6  0.6  0.6  0.3  0.6  0.6  0.3 0.3  1.0
```

---

## Random Shock Events

On every simulation step, each ticker has a 0.1% probability of a **shock event** — a sudden 2–5% jump in either direction. This models unexpected news (earnings surprises, regulatory announcements, macro events) and adds visual variety.

```python
if random.random() < event_probability:  # 0.001 per ticker per tick
    shock_magnitude = random.uniform(0.02, 0.05)
    shock_sign = random.choice([-1, 1])
    price *= 1 + shock_magnitude * shock_sign
```

Expected frequency: with 10 tickers and 2 steps/second:
```
Expected shocks/minute ≈ 10 × 120 × 0.001 = 1.2
```
About one shock per minute across the whole portfolio — noticeable but not overwhelming.

---

## Per-Ticker Parameters

| Ticker | σ (annual vol) | μ (annual drift) | Rationale |
|---|---|---|---|
| AAPL | 0.22 | 0.05 | Large-cap tech |
| GOOGL | 0.25 | 0.05 | Large-cap tech |
| MSFT | 0.20 | 0.05 | Low-vol tech |
| AMZN | 0.28 | 0.05 | High-vol e-commerce |
| TSLA | 0.50 | 0.03 | Extreme vol, lower drift |
| NVDA | 0.40 | 0.08 | High vol, high growth |
| META | 0.30 | 0.05 | Social media |
| JPM | 0.18 | 0.04 | Low-vol financials |
| V | 0.17 | 0.04 | Low-vol payments |
| NFLX | 0.35 | 0.05 | High-vol streaming |
| (default) | 0.25 | 0.05 | Unknown tickers |

Seed prices (starting prices) are set to realistic values close to mid-2024 market levels.

---

## Code Architecture

### GBMSimulator

```python
class GBMSimulator:
    """Pure math: no I/O, no async. Stateless between step() calls."""

    def __init__(self, tickers: list[str], dt: float = DEFAULT_DT,
                 event_probability: float = 0.001) -> None:
        self._dt = dt
        self._event_prob = event_probability
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None
        # Initialize prices and params for each ticker
        self._rebuild_cholesky()

    def step(self) -> dict[str, float]:
        """Advance all prices by one dt. Returns {ticker: new_price}."""
        n = len(self._tickers)
        if n == 0:
            return {}

        # Generate correlated normal variables
        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent if self._cholesky else z_independent

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            mu = self._params[ticker]["mu"]
            sigma = self._params[ticker]["sigma"]
            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            # Random shock event
            if random.random() < self._event_prob:
                shock = random.choice([-1, 1]) * random.uniform(0.02, 0.05)
                self._prices[ticker] *= 1 + shock

            result[ticker] = round(self._prices[ticker], 2)

        return result

    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...
    def get_price(self, ticker: str) -> float | None: ...
    def get_tickers(self) -> list[str]: ...
    def _rebuild_cholesky(self) -> None: ...
```

**Key design:** `GBMSimulator` is **pure** — no async, no I/O, no FastAPI dependencies. It can be unit-tested with deterministic PRNG seeds.

### SimulatorDataSource

```python
class SimulatorDataSource(MarketDataSource):
    """Async wrapper that calls GBM step() on a timer and writes to cache."""

    def __init__(self, price_cache: PriceCache,
                 update_interval: float = 0.5,
                 event_probability: float = 0.001) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers)
        # Seed cache with initial prices
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
        # Start background loop
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def _run_loop(self) -> None:
        while True:
            try:
                prices = self._sim.step()
                for ticker, price in prices.items():
                    self._cache.update(ticker=ticker, price=price)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

### Source Lifecycle Guarantees

- `start()` creates one `GBMSimulator`, seeds `PriceCache` immediately, then starts the background loop.
- The first SSE payload can be sent without waiting for the first 500ms simulation tick.
- `stop()` cancels the task and awaits cancellation so shutdown does not leave a live background task.
- `add_ticker()` seeds the new ticker in the cache immediately after adding it to the simulator.
- `remove_ticker()` removes the ticker from both the simulator and the cache. Higher-level application code must avoid calling this for tickers that still need portfolio valuation.

---

## Initialization Sequence

```
App startup
  ├── PriceCache()                    # Empty cache
  ├── create_market_data_source(cache) # SimulatorDataSource (no key)
  │       └── GBMSimulator(tickers)   # Initializes prices from seed values
  ├── source.start(tickers)
  │       └── cache.update(ticker, seed_price)  # Seeds all initial prices
  └── asyncio.create_task(_run_loop)  # Background task begins
       └── every 500ms: step() → cache.update()
```

The seed prices set the starting point; GBM generates the subsequent path. The first `PriceUpdate` for each ticker has `previous_price == price` (direction = "flat").

---

## Deterministic Testing

For reproducible tests, seed the NumPy PRNG:

```python
import numpy as np

np.random.seed(42)
sim = GBMSimulator(["AAPL", "GOOGL"])
prices1 = sim.step()
prices2 = sim.step()

# With the same seed, step() is deterministic
np.random.seed(42)
sim2 = GBMSimulator(["AAPL", "GOOGL"])
assert sim2.step() == prices1
assert sim2.step() == prices2
```

This allows testing the GBM math without mocking — the output is deterministic given the seed.

---

## Performance

- Single `GBMSimulator.step()` with 10 tickers: ~0.2ms
- NumPy Cholesky decomposition (10×10 matrix): ~0.05ms
- Rebuilding Cholesky on add/remove ticker: < 0.1ms
- 500ms timer resolution: well within real-time constraints

Memory per `GBMSimulator` instance: ~2 KB (prices, params, 10×10 matrix).

## Tests to Keep

- `PriceCache` is seeded on `SimulatorDataSource.start()`.
- `GBMSimulator.step()` never returns negative prices.
- `np.random.seed(...)` makes one or two ticker paths reproducible.
- Cholesky rebuild succeeds for the full default ticker set, not only for 1-2 tickers.
- `add_ticker()` and `remove_ticker()` update simulator ticker state and cache state.
- Background loop cancellation in `stop()` does not leak an unfinished task.

---

## Limitations

1. **No overnight gap:** The model runs continuously. A 5% overnight gap in the real market is not modeled. Over long sessions (hours), simulated prices will have drifted smoothly without the discontinuous jumps that occur at market open.
2. **No microstructure:** Tick-by-tick bid/ask spread, order flow, and market depth are not modeled.
3. **No mean reversion:** In reality, extreme moves tend to partially revert. The simulator has no such mechanism — prices can drift arbitrarily far.
4. **Fixed correlation:** Correlation is static (sector-based). Dynamic correlation (e.g., during a crisis) is not modeled.
5. **Single asset class:** Only equities; no options, futures, or multi-asset correlation.

These limitations are acceptable for a trading workstation demo. For backtesting or quantitative analysis, a more sophisticated model (e.g., Heston stochastic volatility, regime-switching correlation) would be needed.
