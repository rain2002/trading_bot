' BL/S Quantum Trading Desk - Windows Silent Auto-Start Launcher
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\paper_trading_bot"
' Launch PowerShell script silently in the background (0 = hide window, False = don't block)
WshShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File ""D:\paper_trading_bot\scripts\start_dashboard.ps1""", 0, False
