#!/bin/bash
# =============================================================================
# FinAlly — Stop Script (Linux / macOS)
# =============================================================================
# Stops and removes the running FinAlly container.
# The named volume (finally-data) is NOT removed — all data persists.
#
# Usage:
#   ./scripts/stop-linux.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Stopping FinAlly..."
docker stop finally 2>/dev/null || true
docker rm   finally 2>/dev/null || true

echo "FinAlly stopped (database preserved in 'finally-data' volume)."
echo "To remove all data: docker volume rm finally-data"
