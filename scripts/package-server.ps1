# Build web/dist, copy Python libraries into vendor/, write error-analysis-server.zip.
# Run this on Windows PowerShell. Do not use chmod (that is Linux-only).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Out = if ($args.Count -ge 1 -and $args[0]) { $args[0] } else { Join-Path $Root "error-analysis-server.zip" }
$Stage = Join-Path $env:TEMP "error-analysis-server-pack"
$Dest = Join-Path $Stage "error-analysis-server"

function Find-Command([string[]]$Names) {
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

$Npm = Find-Command @("npm.cmd", "npm")
if (-not $Npm) {
    throw "Node.js/npm is required on this machine to build web/dist once. The other laptop will not need Node.js."
}

$Python = Find-Command @("python", "py", "python3")
if (-not $Python) {
    throw "Python 3.10+ is required on this machine to copy libraries into vendor/."
}

$WebDir = Join-Path $Root "web"
if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
    Write-Host "Installing UI dependencies (npm install)..."
    Push-Location $WebDir
    & $Npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
    Pop-Location
}

Write-Host "Building production UI..."
Push-Location $WebDir
& $Npm run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
Pop-Location

$Index = Join-Path $Root "web\dist\index.html"
if (-not (Test-Path $Index)) {
    throw "UI build failed: web\dist\index.html is missing."
}

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Dest | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Dest "web") | Out-Null

Copy-Item (Join-Path $Root "src") (Join-Path $Dest "src") -Recurse
Copy-Item (Join-Path $Root "web\dist") (Join-Path $Dest "web\dist") -Recurse
Copy-Item (Join-Path $Root "web\package.json") (Join-Path $Dest "web\package.json")
foreach ($name in @(
    "pyproject.toml",
    "requirements-runtime.txt",
    "requirements-vendor.txt",
    ".env.example",
    "HOSTING.md",
    "start-server.sh",
    "start-laptop.sh",
    "start-laptop.ps1",
    "Start Error Analysis Laptop.bat"
)) {
    $from = Join-Path $Root $name
    if (Test-Path $from) {
        Copy-Item $from (Join-Path $Dest $name)
    }
}

Get-ChildItem $Dest -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $Dest -Recurse -Include *.pyc, *.pyo | Remove-Item -Force

Write-Host "Vendoring Python modules into the zip (so the other laptop skips venv)..."
$Vendor = Join-Path $Dest "vendor"
& $Python -m pip install --disable-pip-version-check --no-compile `
    -r (Join-Path $Root "requirements-vendor.txt") `
    -t $Vendor
if ($LASTEXITCODE -ne 0) { throw "pip install into vendor\ failed." }

$VendorBin = Join-Path $Vendor "bin"
if (Test-Path $VendorBin) { Remove-Item $VendorBin -Recurse -Force }
$VendorScripts = Join-Path $Vendor "Scripts"
if (Test-Path $VendorScripts) { Remove-Item $VendorScripts -Recurse -Force }
Get-ChildItem $Vendor -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

if (Test-Path $Out) { Remove-Item $Out -Force }
Compress-Archive -Path $Dest -DestinationPath $Out -Force

Write-Host "Wrote $Out"
Write-Host "Send this zip. Do not send .env."
Write-Host "The other laptop must also be Windows (this vendor\ folder is Windows-specific)."
