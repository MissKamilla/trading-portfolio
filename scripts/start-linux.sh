#!/bin/bash
# =============================================================================
# FinAlly — Start Script (Linux / macOS)
# =============================================================================
# Builds the Docker image (if needed or if --build flag is passed) and starts
# the container with the named volume for database persistence.
#
# Usage:
#   ./scripts/start-linux.sh          # start, skip build if image exists
#   ./scripts/start-linux.sh --build  # always rebuild before starting
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# -----------------------------------------------------------------------
# Step 1 — Copy .env.example to .env if .env does not exist yet
# -----------------------------------------------------------------------
if [ ! -f .env ]; then
    echo "No .env found — creating from .env.example (customise before restart if needed)"
    cp .env.example .env
fi

# -----------------------------------------------------------------------
# Step 2 — Build the Docker image (only when necessary)
# -----------------------------------------------------------------------
if [ "$1" = "--build" ] || [ ! -f .dockerbuilt ]; then
    echo "Building Docker image (this may take a few minutes the first time)..."
    docker build --pull -t finally .
    touch .dockerbuilt
    echo "Image built successfully."
fi

# -----------------------------------------------------------------------
# Step 3 — Start (or restart) the container
# -----------------------------------------------------------------------
# Stop any existing container with the same name first so the command is
# idempotent — safe to run whether the container is already running or not.
echo "Starting FinAlly container..."
docker stop finally 2>/dev/null || true
docker rm   finally 2>/dev/null || true

docker run \
    -d \
    --name finally \
    -v finally-data:/app/db \
    -p 8000:8000 \
    --env-file .env \
    --restart unless-stopped \
    finally

# -----------------------------------------------------------------------
# Step 4 — Report
# -----------------------------------------------------------------------
echo ""
echo "FinAlly is running at http://localhost:8000"
echo "View logs:  docker logs finally"
echo "Stop:      ./scripts/stop-linux.sh"
