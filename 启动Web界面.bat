@echo off
chcp 65001 >nul
title 动态选股系统 - Web界面

echo ========================================
echo 动态选股系统 - Web界面
echo ========================================
echo.

REM 设置Python路径（根据用户环境调整）
set PYTHON_PATH=C:\Users\jqlbx\AppData\Local\Programs\Python\Python312\python.exe

REM 检查Python是否存在
if not exist "%PYTHON_PATH%" (
    echo 错误: 找不到Python解释器
    echo 请检查Python路径: %PYTHON_PATH%
    echo 或修改此批处理文件中的PYTHON_PATH变量
    pause
    exit /b 1
)

REM 切换到项目目录
cd /d "%~dp0"

echo 当前目录: %cd%
echo Python路径: %PYTHON_PATH%
echo.

REM 检查Flask依赖
echo 检查Flask依赖...
"%PYTHON_PATH%" -c "import flask" 2>nul
if errorlevel 1 (
    echo 正在安装Flask...
    "%PYTHON_PATH%" -m pip install flask
    if errorlevel 1 (
        echo Flask安装失败
        pause
        exit /b 1
    )
)

echo 依赖检查完成
echo.

REM 启动Web界面
echo 启动Web界面...
echo.
echo 访问地址: http://localhost:5080
echo 按Ctrl+C停止服务
echo.
"%PYTHON_PATH%" web_app.py

echo.
echo ========================================
echo Web服务已停止
echo ========================================
pause