# FinAlly E2E Tests

## Run with Docker (recommended)

```bash
cd finally/test
docker compose -f docker-compose.test.yml up --build
```

This spins up the app container and a Playwright container. Tests run inside the Playwright container against `http://app:8000`.

## Run against a running app

```bash
cd finally/test
npx playwright test
```

Requires the app running at `http://localhost:8000`.

## Run against a local backend (dev mode)

```bash
# Terminal 1: start the app
cd finally
docker compose up --build

# Terminal 2: run tests
cd finally/test
npm install
npx playwright test
```

## Test scenarios

- `smoke.spec.ts`: 14 tests covering:
  - App loads, header visible
  - Default 10-ticker watchlist appears
  - $10,000 starting balance
  - Add/remove watchlist tickers
  - Buy/sell shares and verify cash/positions
  - Insufficient cash validation (409)
  - AI chat returns valid JSON structure
  - Portfolio history and watchlist API shapes
  - Health check
  - Positions table renders after trade
  - SSE connection status dot visible
