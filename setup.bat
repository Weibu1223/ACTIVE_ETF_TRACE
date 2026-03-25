@echo off
chcp 65001 > nul
echo =====================================================
echo  ETF 監控工具 - 安裝設定
echo =====================================================
echo.

REM 檢查 Python 是否已安裝
python --version > nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.8+ 後再執行此腳本
    echo 下載網址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 安裝 Python 套件...
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [錯誤] 套件安裝失敗
    pause
    exit /b 1
)

echo.
echo [2/3] 安裝 Playwright Chromium 瀏覽器...
playwright install chromium
if errorlevel 1 (
    echo [錯誤] Playwright 安裝失敗
    pause
    exit /b 1
)

echo.
echo [3/3] 設定 Windows 工作排程器（每天 09:00 執行）...
echo     正在以系統管理員身分執行排程設定...
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0setup_scheduler.ps1\"' -Verb RunAs -Wait"
if errorlevel 1 (
    echo [警告] 排程設定可能失敗，請查看 PowerShell 視窗中的訊息
) else (
    echo [完成] 排程設定程序已執行
)

echo.
echo =====================================================
echo  安裝完成！
echo  - 測試執行: run.bat
echo  - 查看排程: schtasks /query /tn "%TASK_NAME%"
echo  - 資料目錄: %~dp0data\
echo =====================================================
echo.
pause
