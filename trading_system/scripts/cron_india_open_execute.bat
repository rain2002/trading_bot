@echo off
cd /d "D:\paper_trading_bot"
"D:\paper_trading_bot\venv\Scripts\python.exe" trading_system\scripts\run_dual_pod_paper.py --pod india --phase execute >> trading_system\data\cron_execution.log 2>&1
