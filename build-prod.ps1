# Build the React UI into web/dist for the one-click production app.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Missing .venv. Run: python -m venv .venv && .\.venv\Scripts\pip install -e `".[web]`""
}

Write-Host "Ensuring API package is installed..." -ForegroundColor Cyan
& ".venv\Scripts\pip.exe" install -e ".[web]" | Out-Host

Set-Location "$root\web"
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing UI dependencies (npm install)..." -ForegroundColor Cyan
    npm install
}

Write-Host "Building production UI..." -ForegroundColor Cyan
npm run build

$index = Join-Path $root "web\dist\index.html"
if (-not (Test-Path $index)) {
    Write-Error "Build failed: web\dist\index.html not found."
}

Write-Host ""
Write-Host "Production build ready: web\dist" -ForegroundColor Green
Write-Host "Double-click 'Start Error Analysis.bat' or run .\start-prod.ps1" -ForegroundColor Green
