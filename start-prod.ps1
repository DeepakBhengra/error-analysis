# One-click production launcher: serve UI + API on http://127.0.0.1:8010
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
    Write-Warning ".env not found. Copy .env.example to .env and set credentials."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv and installing package..." -ForegroundColor Cyan
    python -m venv .venv
    & ".venv\Scripts\pip.exe" install -e ".[web]" | Out-Host
}

$index = Join-Path $root "web\dist\index.html"
if (-not (Test-Path $index)) {
    Write-Host "No production UI found — building now..." -ForegroundColor Yellow
    & "$root\build-prod.ps1"
}

# Prod mode: no auto-reload; load package from src/ so a locked .exe reinstall is fine
Remove-Item Env:ERROR_ANALYSIS_RELOAD -ErrorAction SilentlyContinue
$env:ERROR_ANALYSIS_RELOAD = "0"
$env:PYTHONPATH = Join-Path $root "src"

$url = "http://127.0.0.1:8010"
$inUse = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("127.0.0.1", 8010)
    $tcp.Close()
    $inUse = $true
} catch {
    $inUse = $false
}

if ($inUse) {
    Write-Host "Port 8010 is already in use — opening existing app." -ForegroundColor Yellow
    Start-Process $url
    Write-Host "If that is not Error Analysis, stop the other process and run this again."
    pause
    exit 0
}

Write-Host "Starting Error Analysis at $url" -ForegroundColor Cyan
Write-Host "Leave this window open. Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

$opener = Start-Job -ScriptBlock {
    param($Target)
    Start-Sleep -Seconds 2
    Start-Process $Target
} -ArgumentList $url

try {
    & ".venv\Scripts\python.exe" -c "from error_analysis.api import main; main()"
}
finally {
    Stop-Job $opener -ErrorAction SilentlyContinue
    Remove-Job $opener -Force -ErrorAction SilentlyContinue
}
