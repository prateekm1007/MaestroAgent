# bootstrap.ps1 — One-liner entry point for MaestroAgent verification setup
# Downloads setup_automation.ps1 from GitHub and runs it.

$ErrorActionPreference = "Stop"

Write-Host "=== MaestroAgent Verification Bootstrap ===" -ForegroundColor Cyan

# Download setup script
$setupScript = Join-Path $env:TEMP "setup_maestro_automation.ps1"
try {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/prateekm1007/MaestroAgent/main/scripts/setup_automation.ps1" -OutFile $setupScript -UseBasicParsing
    Write-Host "  Downloaded setup_automation.ps1" -ForegroundColor Green
} catch {
    Write-Host "  Failed to download setup script: $_" -ForegroundColor Red
    exit 1
}

# Run setup
& $setupScript

# Cleanup
Remove-Item $setupScript -Force -ErrorAction SilentlyContinue
