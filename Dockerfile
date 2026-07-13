# =============================================================================
# FinAlly — Multi-Stage Docker Build
# =============================================================================
# Stage 1 (builder): Builds the Next.js frontend static export.
#   - Uses Node 20 slim to install deps and run `npm run build`
#   - The build output (static files) is passed to Stage 2 via a named volume
#     or multi-stage COPY. Here we use multi-stage COPY for simplicity.
#
# Stage 2 (runtime): Runs the FastAPI backend and serves static files.
#   - Uses Python 3.12 slim with uv for fast dependency management
#   - Copies backend code, syncs Python dependencies via `uv sync`
#   - Copies the Stage 1 static export into /app/static/ (served by FastAPI)
#   - Sets working directory to /app and exposes port 8000
#   - CMD starts uvicorn serving app.main:app
#
# Build:
#   docker build -t finally .
#
# Run:
#   docker run -v finally-data:/app/db -p 8000:8000 --env-file .env --name finally finally
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Frontend Builder
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Copy only package files first (layer cache optimisation)
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; \
    else echo "No package-lock.json found — running npm install"; npm install; fi

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime (FastAPI + Python)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Install uv globally (avoids per-project installation overhead)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Set Python to run unbuffered so logs appear in docker logs immediately
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Copy backend project files
COPY backend/pyproject.toml backend/uv.lock* backend/README.md ./
RUN uv sync --frozen

# Copy backend source code
COPY backend/app/ ./app/

# Copy static frontend build output from Stage 1 into FastAPI's static dir
COPY --from=frontend-builder /build/out ./static/

# Create the db directory so the volume mount target exists at runtime
RUN mkdir -p /app/db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
