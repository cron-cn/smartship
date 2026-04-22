#!/usr/bin/env pwsh
# start_env.ps1 - Reliable PowerShell startup script for Windows
# Usage (from cmd or PowerShell):
#   powershell -ExecutionPolicy Bypass -File start_env.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Script root directory
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Working directory: $Root"

# Force UTF-8 output encoding for console
[Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8

# Function to find available Python command
function Find-Python {
    $py = (& where.exe py 2>$null) -split "\r?\n" | Select-Object -First 1
    if ($py) { return @{exe = 'py'; cmd = 'py -3'} }
    $python = (& where.exe python 2>$null) -split "\r?\n" | Select-Object -First 1
    if ($python) { return @{exe = 'python'; cmd = 'python'} }
    return $null
}

$found = Find-Python
if (-not $found) {
    Write-Host "Python not found. Please install Python 3.11+ from https://www.python.org and enable 'Add Python to PATH'." -ForegroundColor Yellow
    exit 1
}
Write-Host "Using Python command: $($found.cmd)"

# Virtual environment paths
$VenvDir = Join-Path $Root '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

if (-Not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found, creating at: $VenvDir ..."
    try {
        & $found.cmd -m venv "$VenvDir"
    } catch {
        Write-Host "Failed to create virtual environment: $_" -ForegroundColor Red
        exit 1
    }
}

if (-Not (Test-Path $VenvPython)) {
    Write-Host "Python executable not found in virtual environment: $VenvPython" -ForegroundColor Red
    exit 1
}

# Health check: ensure venv python is runnable; if not, delete and recreate
try {
    & $VenvPython -c 'import sys; print("ok")' 2>$null
} catch {
    Write-Host "Detected broken virtual environment; recreating at: $VenvDir" -ForegroundColor Yellow
    try {
        Remove-Item -Recurse -Force -LiteralPath $VenvDir
    } catch {
        Write-Host "Failed to remove existing venv: $_" -ForegroundColor Red
    }
    try {
        & $found.cmd -m venv "$VenvDir"
    } catch {
        Write-Host "Failed to recreate virtual environment: $_" -ForegroundColor Red
        exit 1
    }
    if (-Not (Test-Path $VenvPython)) {
        Write-Host "Recreated venv but python still missing: $VenvPython" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Virtual environment ready: $VenvDir"

# Upgrade pip and install requirements if present
Write-Host "Upgrading pip, setuptools, wheel..."
& $VenvPython -m pip install --upgrade pip setuptools wheel | Out-Null

$ReqFile = Join-Path $Root 'hub\requirements.txt'
if (Test-Path $ReqFile) {
    Write-Host "Installing requirements from: $ReqFile"
    & $VenvPython -m pip install -r "$ReqFile"
} else {
    Write-Host "No requirements file found at $ReqFile, skipping dependency install."
}

# Start the app using venv python in a new process
$AppScript = Join-Path $Root 'hub\app.py'
if (-Not (Test-Path $AppScript)) {
    Write-Host "App script not found: $AppScript" -ForegroundColor Red
    exit 1
}

Write-Host "Selecting an available port..."
# Determine host (allow remote binding if environment variable ALLOW_REMOTE == '1')
$Host = if ($env:ALLOW_REMOTE -eq '1') { '0.0.0.0' } else { '127.0.0.1' }

# Find a free TCP port on loopback
$listener = [System.Net.Sockets.TcpListener]::New([System.Net.IPAddress]::Loopback,0)
$listener.Start()
$Port = ($listener.LocalEndpoint).Port
$listener.Stop()

Write-Host "Chosen host: $Host  port: $Port"

Write-Host "Starting application: $AppScript with host=$Host port=$Port ..."
$argsList = @($AppScript, '--host', $Host, '--port', [string]$Port)
$proc = Start-Process -FilePath $VenvPython -ArgumentList $argsList -WorkingDirectory $Root -WindowStyle Normal -PassThru
Write-Host "Process started with Id=$($proc.Id)"

# Wait for service readiness (up to 30 seconds) using localhost for browser
$ServerUrl = "http://localhost:$Port"
Write-Host "Waiting for service to become available at: $ServerUrl"
$ready = $false
for ($i=0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $ServerUrl -UseBasicParsing -Method Head -TimeoutSec 2 -ErrorAction Stop
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

if ($ready) {
    Write-Host "Service is up, opening default browser..."
    Start-Process $ServerUrl
} else {
    Write-Host "Service did not respond in time; please open $ServerUrl manually." -ForegroundColor Yellow
}

Write-Host "Done. Press any key to exit..."
[void][System.Console]::ReadKey($true)
