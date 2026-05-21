@echo off
chcp 65001 >nul
title 动态选股系统 - 高频交易与10倍股筛选

echo ========================================
echo 动态选股系统 - 高频交易与10倍股筛选
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

REM 检查依赖
echo 检查依赖包...
"%PYTHON_PATH%" -c "import akshare, pandas, numpy" 2>nul
if errorlevel 1 (
    echo 正在安装依赖包...
    "%PYTHON_PATH%" -m pip install akshare pandas numpy
    if errorlevel 1 (
        echo 依赖包安装失败
        pause
        exit /b 1
    )
)

echo 依赖检查完成
echo.

REM 运行主程序
echo 启动选股系统...
echo.
"%PYTHON_PATH%" main.py

echo.
echo ========================================
echo 选股完成！
echo ========================================
echo.
echo 结果文件保存在: output目录
echo 日志文件保存在: logs目录
echo.
pause