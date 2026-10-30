@echo off
title BL/S Quantum Trading Desk
cd /d "D:\paper_trading_bot"
echo =====================================================================
echo  BL/S Quantum Trading Desk - Digital Trading Terminal
echo  Dashboard URL: http://localhost:8501
echo =====================================================================

set "PY_EXE=python"
where python >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\Program Files\Python313\python.exe" (
        set "PY_EXE=C:\Program Files\Python313\python.exe"
    )
)

netstat -ano | findstr :8501 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo [OK] Dashboard already active! Opening browser...
    start "" http://localhost:8501
    exit /b
)

start "" http://localhost:8501
"%PY_EXE%" -m streamlit run "trading_system\dashboard.py" --server.port 8501
pause
