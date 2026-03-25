# ETF 監控排程器設定腳本（PowerShell）
# 以系統管理員身分執行此腳本

# 檢查是否有管理員權限，若無則自動提升
$currentUser = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "需要管理員權限，正在重新以管理員身分執行..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$scriptPath`""
    exit
}

$TaskName = "ETF_Monitor_Daily"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "etf_monitor.py"
$LogFile = Join-Path $ScriptDir "data\run.log"

# 取得 python 執行路徑
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) {
    Write-Host "錯誤：找不到 Python，請先安裝 Python 3.8+" -ForegroundColor Red
    exit 1
}

Write-Host "Python 路徑: $PythonPath" -ForegroundColor Cyan
Write-Host "腳本路徑: $PythonScript" -ForegroundColor Cyan
Write-Host "日誌路徑: $LogFile" -ForegroundColor Cyan

# 建立 Action（執行 Python 腳本並輸出至 log）
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c chcp 65001 > nul && python `"$PythonScript`" >> `"$LogFile`" 2>&1" `
    -WorkingDirectory $ScriptDir

# 設定觸發條件：週一到週五 09:00
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "09:00AM"

# 設定條件：只有在有網路連線時才執行
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# 刪除舊排程
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# 建立排程
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "每天 09:00 爬取 ETF 前10大持股並記錄差異" `
        -RunLevel Highest

    Write-Host "`n[成功] 工作排程器設定成功！" -ForegroundColor Green
    Write-Host "  任務名稱: $TaskName"
    Write-Host "  每天 09:00 自動執行"
    Write-Host "  日誌輸出: $LogFile"
    Write-Host "`n查詢排程狀態: Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "立即執行一次: Start-ScheduledTask -TaskName '$TaskName'"
} catch {
    Write-Host "錯誤：排程設定失敗 - $_" -ForegroundColor Red
    Write-Host "請以系統管理員身分重新執行此腳本" -ForegroundColor Yellow
}
