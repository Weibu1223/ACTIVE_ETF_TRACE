@echo off
chcp 65001 > nul
echo =====================================================
echo  ETF 監控 - 設定工作排程器
echo =====================================================
echo.
echo 正在以系統管理員身分執行排程設定...
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0setup_scheduler.ps1\"' -Verb RunAs -Wait"
echo.
echo 排程設定程序已執行，請查看剛才彈出的 PowerShell 視窗結果。
echo.
pause
