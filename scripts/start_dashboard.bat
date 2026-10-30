@echo off
title BL/S Quantum Trading Desk - Terminal
cd /d "D:\paper_trading_bot"

set "PY_EXE=C:\Program Files\Python313\python.exe"
if not exist "%PY_EXE%" (
    set "PY_EXE=python"
)

netstat -ano | findstr :8501 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo [OK] Trading Desk server is already active on port 8501!
    start "" http://localhost:8501
    exit /b
)

start "BL/S Quantum Trading Server (Port 8501)" "%PY_EXE%" -m streamlit run "trading_system\dashboard.py" --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false

:WAIT_LOOP
timeout /t 1 /nobreak >nul
netstat -ano | findstr :8501 | findstr LISTENING >nul
if %errorlevel% neq 0 goto WAIT_LOOP

start "" http://localhost:8501
