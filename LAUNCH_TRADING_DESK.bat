@echo off
title BL/S Quantum Trading Desk - Terminal
cd /d "D:\paper_trading_bot"

echo ===============================================================================
echo   BL/S QUANTUM TRADING DESK // DIGITAL TRADING TERMINAL
echo   Connected Directly to Live Backend (US Alpaca + India Groww)
echo ===============================================================================
echo.

:: Detect Python executable
set "PY_EXE=C:\Program Files\Python313\python.exe"
if not exist "%PY_EXE%" (
    set "PY_EXE=python"
)

:: Check if server is already running on port 8501
netstat -ano | findstr :8501 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo [OK] Trading Desk server is already active on port 8501!
    echo [OK] Launching browser at http://localhost:8501...
    start "" http://localhost:8501
    timeout /t 2 >nul
    exit /b
)

echo [1/3] Loading live backend environment (.env)...
if exist ".env" (
    echo   [OK] Broker API credentials loaded.
) else (
    echo   [WARNING] .env credentials file not found.
)

echo [2/3] Starting Quantum Trading Server...
:: Launch Streamlit server in a dedicated window
start "BL/S Quantum Trading Server (Port 8501)" "%PY_EXE%" -m streamlit run "trading_system\dashboard.py" --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false

echo [3/3] Waiting for server to initialize...
set /a retries=0

:WAIT_LOOP
timeout /t 1 /nobreak >nul
set /a retries+=1
netstat -ano | findstr :8501 | findstr LISTENING >nul
if %errorlevel% neq 0 (
    if %retries% geq 20 (
        echo [ERROR] Server startup timed out. Check console for details.
        pause
        exit /b 1
    )
    echo   Initializing quantum pipeline (attempt %retries%/20)...
    goto WAIT_LOOP
)

echo.
echo ===============================================================================
echo  [READY] Quantum Trading Desk is LIVE!
echo  Opening browser at http://localhost:8501
echo ===============================================================================
start "" http://localhost:8501
timeout /t 3 >nul
