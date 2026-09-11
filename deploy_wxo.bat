@echo off
title NutriAI — Deploy to watsonx Orchestrate
color 0B

echo.
echo  ====================================================
echo    NutriAI — Deploy Agent to IBM watsonx Orchestrate
echo  ====================================================
echo.

:: ── Check if orchestrate CLI is available ─────────────────────────────────────
where orchestrate >nul 2>&1
if errorlevel 1 (
    echo  [INFO]  orchestrate CLI not found. Trying via venv...
    if exist "%~dp0venv\Scripts\orchestrate.exe" (
        set ORCH=%~dp0venv\Scripts\orchestrate
    ) else (
        echo  [ERROR] orchestrate CLI not found.
        echo  [INFO]  Install with: pip install ibm-watsonx-orchestrate
        pause & exit /b 1
    )
) else (
    set ORCH=orchestrate
)

:: ── Activate venv ─────────────────────────────────────────────────────────────
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
)

echo  [STEP 1] Checking active environment...
%ORCH% env list
echo.

echo  [STEP 2] Importing nutrition tools...
%ORCH% tools import -k python -f "%~dp0tools\nutrition_tools.py" --requirements "%~dp0tools\requirements.txt"
if errorlevel 1 (
    echo  [WARN] Tool import had errors. Check output above.
) else (
    echo  [OK] Tools imported successfully.
)
echo.

echo  [STEP 3] Importing nutrition agent...
%ORCH% agents import -f "%~dp0agent\nutrition_agent.yaml"
if errorlevel 1 (
    echo  [WARN] Agent import had errors. Check output above.
) else (
    echo  [OK] Agent imported successfully.
)
echo.

echo  ====================================================
echo    Deployment complete!
echo    Open watsonx Orchestrate UI and search for:
echo    "nutrition-agent"
echo  ====================================================
echo.
pause
