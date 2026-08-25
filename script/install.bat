@echo off
rem 一键安装:创建虚拟环境并安装依赖。使用方法:双击本文件,或运行 install.bat
setlocal
cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo 错误:未找到 Python。请先安装 Python 3.9+ 并在安装时勾选 "Add Python to PATH"。
        pause
        exit /b 1
    )
)

echo.
echo 请确认:如需读取 iPhone 电池温度,请确保已安装 Apple iTunes/驱动(提供 usbmux 服务)。
echo.

%PY% -m venv .venv
if errorlevel 1 (
    echo 创建虚拟环境失败。
    pause
    exit /b 1
)

.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo 安装依赖失败。
    pause
    exit /b 1
)

echo.
echo 安装完成。运行 run.bat 启动监控。
pause