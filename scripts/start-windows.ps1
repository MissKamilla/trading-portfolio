# =============================================================================
# FinAlly — Start Script (Windows PowerShell)
# =============================================================================
# Builds the Docker image (if needed or if -Build flag is passed) and starts
# the container with the named volume for database persistence.
#
# Usage:
#   .\scripts\start-windows.ps1          # start, skip build if image exists
#   .\scripts\start-windows.ps1 -Build    # always rebuild before starting
# =============================================================================

param(
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot

try {
    # -----------------------------------------------------------------------
    # Step 1 — Copy .env.example to .env if .env does not exist yet
    # -----------------------------------------------------------------------
    if (-not (Test-Path .env)) {
        Write-Host "No .env found — creating from .env.example (customise before restart if needed)" -ForegroundColor Yellow
        Copy-Item .env.example .env
    }

    # -----------------------------------------------------------------------
    # Step 2 — Build the Docker image (only when necessary)
    # -----------------------------------------------------------------------
    $buildMarker = Join-Path $ProjectRoot ".dockerbuilt"
    if ($Build -or -not (Test-Path $buildMarker)) {
        Write-Host "Building Docker image (this may take a few minutes the first time)..." -ForegroundColor Cyan
        docker build --pull -t finally .
        # Suppress error in case of permission issues with the marker file
        try { New-Item -Path $buildMarker -ItemType File -Force | Out-Null } catch {}
        Write-Host "Image built successfully." -ForegroundColor Green
    }

    # -----------------------------------------------------------------------
    # Step 3 — Start (or restart) the container
    # -----------------------------------------------------------------------
    Write-Host "Starting FinAlly container..." -ForegroundColor Cyan

    # Stop any existing container with the same name (idempotent)
    docker stop finally 2>$null
    docker rm   finally 2>$null

    docker run `
        -d `
        --name finally `
        -v finally-data:/app/db `
        -p 8000:8000 `
        --env-file .env `
        --restart unless-stopped `
        finally

    # -----------------------------------------------------------------------
    # Step 4 — Report
    # -----------------------------------------------------------------------
    Write-Host ""
    Write-Host "FinAlly is running at http://localhost:8000" -ForegroundColor Green
    Write-Host "View logs:  docker logs finally"
    Write-Host "Stop:       .\scripts\stop-windows.ps1"

} finally {
    Pop-Location
}
