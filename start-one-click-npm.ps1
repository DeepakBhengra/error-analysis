# One-click start for the server: system Python (no venv) + npm-built UI.
# Same launcher behavior as the one-click start script (host/port, import check,
# open browser). Same UI build as build-prod.ps1 (npm install / npm run build)
# without creating or using .venv.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$python = "C:\Program Files\Python312\python.exe"
$listenHost = "10.24.169.28"
$listenPort = 7009
$url = "http://${listenHost}:${listenPort}"

if (-not (Test-Path $python)) {
    $fallback = Get-Command python -ErrorAction SilentlyContinue
    if ($fallback) {
        $python = $fallback.Source
    } else {
        throw "Python not found at '$python'. Install Python 3.12 or add python to PATH."
    }
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npm) {
    throw "Node.js/npm is required on this machine to build web\dist (same as build-prod.ps1)."
}

if (-not (Test-Path ".env")) {
    Write-Warning ".env not found. Copy .env.example to .env and set credentials."
}

# --- same npm steps as build-prod.ps1 (no venv / pip) ---
Set-Location "$root\web"
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing UI dependencies (npm install)..." -ForegroundColor Cyan
    & $npm.Source install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
}
Write-Host "Building production UI..." -ForegroundColor Cyan
& $npm.Source run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
Set-Location $root

$index = Join-Path $root "web\dist\index.html"
if (-not (Test-Path $index)) {
    throw "Build failed: web\dist\index.html not found."
}
Write-Host "Production UI ready: web\dist" -ForegroundColor Green

# --- same one-click start attributes (system Python, no venv) ---
Write-Host "Checking Python dependencies..." -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $root "src"
$env:ERROR_ANALYSIS_RELOAD = "0"
$env:ERROR_ANALYSIS_HOST = $listenHost
$env:ERROR_ANALYSIS_PORT = "$listenPort"

& $python -c "import fastapi, uvicorn; from error_analysis.api import main"
if ($LASTEXITCODE -ne 0) {
    throw "Required Python dependencies or application imports are missing. Install them using the approved deployment process."
}

$inUse = $false
$tcp = New-Object System.Net.Sockets.TcpClient
try {
    $tcp.Connect($listenHost, $listenPort)
    $inUse = $true
} catch {
    $inUse = $false
} finally {
    $tcp.Dispose()
}

if ($inUse) {
    Write-Host "Port $listenPort is already in use - opening existing app." -ForegroundColor Yellow
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
    & $python -c "from error_analysis.api import main; main()"
} finally {
    Stop-Job $opener -ErrorAction SilentlyContinue
    Remove-Job $opener -Force -ErrorAction SilentlyContinue
}
