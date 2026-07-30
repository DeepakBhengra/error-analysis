# Start Order Replay API (8010) and Vite UI (5173+) together.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\error-analysis-api.exe")) {
    Write-Error "Run: python -m venv .venv && pip install -e `".[web,dev]`""
}

$env:ERROR_ANALYSIS_RELOAD = "1"
$api = Start-Process -FilePath ".venv\Scripts\error-analysis-api.exe" `
    -WorkingDirectory $root -PassThru -WindowStyle Minimized

Write-Host "API starting on http://127.0.0.1:8010 (pid $($api.Id))" -ForegroundColor Cyan
Start-Sleep -Seconds 2

Set-Location "$root\web"
Write-Host "Starting Vite UI (proxies /api -> :8010)..." -ForegroundColor Cyan
npm run dev
