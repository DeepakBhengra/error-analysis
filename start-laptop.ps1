# Run the packaged app on a Windows laptop that has only Python
# (no Node.js, no venv). Requires web/dist and vendor/ from package-server.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$HostBind = if ($env:ERROR_ANALYSIS_HOST) { $env:ERROR_ANALYSIS_HOST } else { "127.0.0.1" }
$Port = if ($env:ERROR_ANALYSIS_PORT) { $env:ERROR_ANALYSIS_PORT } else { "8010" }
$env:ERROR_ANALYSIS_HOST = $HostBind
$env:ERROR_ANALYSIS_PORT = "$Port"

$Index = Join-Path $Root "web\dist\index.html"
if (-not (Test-Path $Index)) {
    Write-Error "Missing web\dist\index.html. Ask the sender to run scripts/package-server.sh (or .ps1) on a matching OS."
}

$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing .env. Copy .env.example to .env and set Datadog / Order Create credentials."
}

$Python = $null
foreach ($candidate in @("py", "python", "python3")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $Python = $cmd.Source
        break
    }
}
if (-not $Python) {
    Write-Error "Python 3.10+ is required (python or py on PATH). Node.js is not required."
}

$Vendor = Join-Path $Root "vendor"
$Src = Join-Path $Root "src"
$env:PYTHONPATH = if (Test-Path $Vendor) { "$Src;$Vendor" } else { "$Src" }

& $Python -c "import fastapi, uvicorn, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python packages were not found in vendor\. Rebuild the zip on the same OS as this laptop (Windows zip for Windows, Linux zip for Linux)."
}

Write-Host "Starting Error Analysis on http://${HostBind}:${Port}"
& $Python -m uvicorn error_analysis.api:app --host $HostBind --port $Port
