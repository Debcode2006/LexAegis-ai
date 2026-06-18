# Start the FastAPI backend with hot reload (Windows / PowerShell).
$ErrorActionPreference = "Stop"

$backend = Join-Path $PSScriptRoot "..\backend"
Set-Location $backend

if (-not $env:HOST) { $env:HOST = "0.0.0.0" }
if (-not $env:PORT) { $env:PORT = "8000" }
$env:PYTHONPATH = "."

uvicorn app.main:app --reload --host $env:HOST --port $env:PORT
