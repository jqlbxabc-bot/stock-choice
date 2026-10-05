@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动A股实时选股...
python realtime_selector.py
pause
