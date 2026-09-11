@echo off
title NutriAI — Nutrition Agent
color 0A

echo.
echo  ====================================================
echo    NutriAI — Personal Nutrition Agent
echo    Powered by IBM watsonx AI
echo  ====================================================
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
    pause & exit /b 1
)

:: ── Activate venv if it exists, else use global python ────────────────────────
if exist "%~dp0venv\Scripts\activate.bat" (
    echo  [INFO]  Activating virtual environment...
    call "%~dp0venv\Scripts\activate.bat"
) else (
    echo  [WARN]  No venv found — using system Python.
)

:: ── Install / verify backend dependencies ─────────────────────────────────────
echo  [INFO]  Checking backend dependencies...
pip install fastapi uvicorn[standard] httpx pydantic python-dotenv --quiet

:: ── Set watsonx token ─────────────────────────────────────────────────────────
set WATSONX_APIKEY=iEcAYr__w_EdxG7RTUOM2fZ-uPSaaL-d3_8GLRyUrG63

:: ── Launch backend ────────────────────────────────────────────────────────────
echo.
echo  [INFO]  Starting NutriAI backend on http://localhost:8000 ...
echo  [INFO]  API docs: http://localhost:8000/docs
echo  [INFO]  Frontend: http://localhost:8000
echo  [INFO]  Press Ctrl+C to stop.
echo.

cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
