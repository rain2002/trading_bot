@echo off
title BL/S Quantum Trading Desk
cd /d "D:\paper_trading_bot"
echo =====================================================================
echo  BL/S Quantum Trading Desk - Digital Trading Terminal
echo  Dashboard URL: http://localhost:8501
echo =====================================================================
"D:\paper_trading_bot\venv\Scripts\streamlit.exe" run "trading_system\dashboard.py" --server.port 8501
pause
