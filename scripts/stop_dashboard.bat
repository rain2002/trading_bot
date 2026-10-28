@echo off
title Stop BL/S Quantum Trading Desk
echo Stopping BL/S Quantum Trading Desk Dashboard on port 8501...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo Dashboard stopped.
timeout /t 2 >nul
