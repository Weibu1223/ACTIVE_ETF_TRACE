@echo off
chcp 65001 > nul
echo 正在執行 ETF 持股監控...
echo.
python "%~dp0etf_monitor.py"
echo.
pause
