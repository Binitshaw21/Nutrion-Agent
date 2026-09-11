# NutriAI -- Startup Script (PowerShell)
# Usage: .\run.ps1

Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Green
Write-Host "    NutriAI -- Personal Nutrition Agent"               -ForegroundColor Green
Write-Host "    Powered by IBM watsonx AI"                         -ForegroundColor Green
Write-Host "  ====================================================" -ForegroundColor Green
Write-Host ""

# Use the venv python directly so we never hit the wrong interpreter
$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
    Write-Host "  [INFO]  Using venv Python: $python" -ForegroundColor Cyan
} else {
    $python = "python"
    Write-Host "  [WARN]  venv not found, using system Python." -ForegroundColor Yellow
}

# IBM Cloud API key -- used to auto-fetch and refresh Bearer tokens
$env:WATSONX_APIKEY = "iEcAYr__w_EdxG7RTUOM2fZ-uPSaaL-d3_8GLRyUrG63"

# Install / upgrade backend deps into the venv
Write-Host "  [INFO]  Installing dependencies..." -ForegroundColor Cyan
& $python -m pip install fastapi "uvicorn[standard]" httpx pydantic python-dotenv --quiet

Write-Host ""
Write-Host "  [INFO]  Backend   -> http://localhost:8000"      -ForegroundColor Green
Write-Host "  [INFO]  API docs  -> http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  [INFO]  Frontend  -> http://localhost:8000"      -ForegroundColor Green
Write-Host "  [INFO]  Press Ctrl+C to stop."                   -ForegroundColor Yellow
Write-Host ""

Set-Location (Join-Path $PSScriptRoot "backend")
& $python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
