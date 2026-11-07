<#
.SYNOPSIS
    Registers the 4 daily automated trading jobs for India & US Dual-Pod forward paper trading in Windows Task Scheduler.
.DESCRIPTION
    Schedule (IST Clocks):
      - 09:14 IST (Mon-Fri) : Pod 1 (India) Morning Open Execution
      - 15:35 IST (Mon-Fri) : Pod 1 (India) Evening Close Scan & Rebalance
      - 19:59 IST (Mon-Fri) : Pod 2 (US / Alpaca) Morning Open Execution (09:29 EST)
      - 02:35 IST (Tue-Sat) : Pod 2 (US / Alpaca) Evening Close Scan & Rebalance (16:05 EST)
#>

$root = "D:\paper_trading_bot"
$scriptsDir = "$root\trading_system\scripts"

Write-Host "Registering Dual-Pod 13-Week Forward Paper Trading Scheduled Tasks..." -ForegroundColor Cyan

# 1. India Open Execute (09:14 IST)
schtasks /create /tn "TradingBot_India_Open_Execute" /tr "$scriptsDir\cron_india_open_execute.bat" /sc weekly /d MON,TUE,WED,THU,FRI /st 09:14 /f
Write-Host "[OK] Task 'TradingBot_India_Open_Execute' registered (09:14 IST Mon-Fri)" -ForegroundColor Green

# 2. India Close Scan (15:35 IST)
schtasks /create /tn "TradingBot_India_Close_Scan" /tr "$scriptsDir\cron_india_close_scan.bat" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:35 /f
Write-Host "[OK] Task 'TradingBot_India_Close_Scan' registered (15:35 IST Mon-Fri)" -ForegroundColor Green

# 3. US Open Execute (19:59 IST / 09:29 EST)
schtasks /create /tn "TradingBot_US_Open_Execute" /tr "$scriptsDir\cron_us_open_execute.bat" /sc weekly /d MON,TUE,WED,THU,FRI /st 19:59 /f
Write-Host "[OK] Task 'TradingBot_US_Open_Execute' registered (19:59 IST Mon-Fri)" -ForegroundColor Green

# 4. US Close Scan (02:35 IST / 16:05 EST)
schtasks /create /tn "TradingBot_US_Close_Scan" /tr "$scriptsDir\cron_us_close_scan.bat" /sc weekly /d TUE,WED,THU,FRI,SAT /st 02:35 /f
Write-Host "[OK] Task 'TradingBot_US_Close_Scan' registered (02:35 IST Tue-Sat)" -ForegroundColor Green

Write-Host "`nAll 4 automated trading tasks successfully scheduled!" -ForegroundColor Cyan
Write-Host "View active status anytime by running:"
Write-Host "  venv\Scripts\python.exe trading_system\scripts\run_dual_pod_paper.py --phase status" -ForegroundColor Yellow
