@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo A股交易助手 - Windows EXE 构建
echo ==========================================

where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python。请先安装 Python 3.11 或 3.12，并勾选 Add Python to PATH。
  pause
  exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

if errorlevel 1 (
  echo 依赖安装失败。
  pause
  exit /b 1
)

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

python -m PyInstaller --clean "A股交易助手.spec"

if errorlevel 1 (
  echo 构建失败，请把本窗口最后30行错误发给 ChatGPT。
  pause
  exit /b 1
)

echo.
echo 构建完成：
echo %CD%\dist\A股交易助手.exe
echo.
start "" "%CD%\dist"
pause
