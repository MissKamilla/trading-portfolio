# FinAlly — AI Trading Workstation

A visually stunning AI-powered trading simulator with live market data, portfolio management, and an LLM chat assistant.

## Quick Start

```bash
docker build -t finally .
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

Open [http://localhost:8000](http://localhost:8000)

## Features

- **Live price streaming** — prices flash green/red on change, sparkline charts per ticker
- **Market orders** — buy/sell with instant fill, no fees, $10,000 virtual cash
- **Portfolio** — treemap heatmap, P&L chart, positions table
- **AI chat** — ask the assistant to analyze positions, execute trades, manage watchlist
- **SSE streaming** — real-time updates, auto-reconnect

## Architecture

- **Frontend**: Next.js (static export) + Tailwind, dark terminal aesthetic
- **Backend**: FastAPI (Python/uv), SQLite, SSE
- **AI**: LiteLLM → OpenRouter (Cerebras), structured outputs
- **Data**: Market simulator (default) or Massive API via `MASSIVE_API_KEY`

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | OpenRouter key for real AI chat |
| `OPENROUTER_MODEL` | `openrouter/openai/gpt-oss-120b` | Model ID |
| `MASSIVE_API_KEY` | — | Real market data (simulator if unset) |
| `LLM_MOCK` | `true` | Use mock LLM responses |

## Scripts

```bash
./scripts/start-linux.sh   # Build & run container
./scripts/stop-linux.sh   # Stop container (data persists)
```
