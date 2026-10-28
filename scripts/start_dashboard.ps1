# BL/S Quantum Trading Desk - Auto-Start Script
$workDir = "D:\paper_trading_bot"
Set-Location -Path $workDir

# Verify if Streamlit is already active on port 8501
$activeConnection = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue

if (-not $activeConnection) {
    $streamlitExe = "D:\paper_trading_bot\venv\Scripts\streamlit.exe"
    $dashboardScript = "D:\paper_trading_bot\trading_system\dashboard.py"

    # Start Streamlit silently in the background
    Start-Process -FilePath $streamlitExe `
                  -ArgumentList "run `"$dashboardScript`" --server.port 8501 --server.headless true" `
                  -WorkingDirectory $workDir `
                  -WindowStyle Hidden
}
