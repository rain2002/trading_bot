@echo off
title BL/S Quantum Trading Desk - Terminal
cd /d "D:\paper_trading_bot"

echo ===============================================================================
echo   BL/S QUANTUM TRADING DESK // DIGITAL TRADING TERMINAL
echo   Connected Directly to Live Backend (US Alpaca + India Groww)
echo ===============================================================================
echo.

:: Detect Python executable
set "PY_EXE=python"
where python >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\Program Files\Python313\python.exe" (
        set "PY_EXE=C:\Program Files\Python313\python.exe"
    )
)

echo [1/3] Verifying Backend Configuration (.env)...
if not exist ".env" (
    echo   [WARNING] .env credentials file not found in workspace root.
) else (
    echo   [OK] Live Broker Credentials & Settings Loaded (.env)
)

echo.
echo [2/3] Checking if Trading Desk is already running on port 8501...
netstat -ano | findstr :8501 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo   [OK] Terminal is already active!
    echo [3/3] Opening Trading Desk in your default web browser...
    start "" http://localhost:8501
    timeout /t 3 >nul
    exit /b
)

echo   [OK] Initializing Fresh Frontend Session...
echo.
echo [3/3] Launching Quantum Trading Terminal at http://localhost:8501...
start "" http://localhost:8501

"%PY_EXE%" -m streamlit run "trading_system\dashboard.py" --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
