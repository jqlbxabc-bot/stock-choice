@echo off
chcp 65001 >nul
cd /d "%~dp0"
python sync_dashboard.py
echo.
echo 看板数据已更新到 dashboard\data.json
echo 如需发布云端，请在本仓库执行 git add/commit/push。
pause
