@echo off
rem 一键启动:启动监控服务并自动打开浏览器。使用方法:双击本文件,或运行 run.bat
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo 未找到虚拟环境。请先运行 install.bat。
    pause
    exit /b 1
)

echo 正在启动 iPhone 电池温度监控 ...
.venv\Scripts\python main.py --open
pause