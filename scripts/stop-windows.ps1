# =============================================================================
# FinAlly — Stop Script (Windows PowerShell)
# =============================================================================
# Stops and removes the running FinAlly container.
# The named volume (finally-data) is NOT removed — all data persists.
#
# Usage:
#   .\scripts\stop-windows.ps1
# =============================================================================

$ErrorActionPreference = 'Stop'

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR

Push-Location $PROJECT_ROOT

try {
    Write-Host "Stopping FinAlly..." -ForegroundColor Cyan
    docker stop finally 2>$null
    docker rm   finally 2>$null
    Write-Host "FinAlly stopped (database preserved in 'finally-data' volume)." -ForegroundColor Green
    Write-Host "To remove all data: docker volume rm finally-data"

} finally {
    Pop-Location
}
