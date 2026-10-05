@echo off
chcp 65001 >nul
cd /d "%~dp0"

python sync_dashboard.py
if errorlevel 1 (
  echo 看板数据生成失败。
  pause
  exit /b 1
)

git add dashboard/data.json docs/data.json
git diff --cached --quiet
if not errorlevel 1 (
  echo 没有新的看板数据，无需推送。
  pause
  exit /b 0
)

git commit -m "Update trading dashboard data"
git push origin main

echo.
echo 云端看板数据已推送。
pause
