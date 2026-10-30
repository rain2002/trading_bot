# BL/S Quantum Trading Desk - Auto-Start Script
$workDir = "D:\paper_trading_bot"
Set-Location -Path $workDir

# Verify if Streamlit is already active on port 8501
$activeConnection = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue

if ($activeConnection) {
    Write-Host "[OK] Trading Desk already running on port 8501. Launching browser..."
    Start-Process "http://localhost:8501"
} else {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonExe -and (Test-Path "C:\Program Files\Python313\python.exe")) {
        $pythonExe = "C:\Program Files\Python313\python.exe"
    }

    $dashboardScript = "trading_system\dashboard.py"

    Write-Host "[OK] Starting Quantum Trading Terminal on http://localhost:8501..."
    Start-Process "http://localhost:8501"

    # Start Streamlit in foreground/normal window
    Start-Process -FilePath $pythonExe `
                  -ArgumentList "-m streamlit run `"$dashboardScript`" --server.port 8501 --server.headless false" `
                  -WorkingDirectory $workDir
}
