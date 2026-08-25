#!/usr/bin/env bash
# 一键安装:创建虚拟环境并安装依赖。用法:bash script/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."          # 定位到项目根,允许从任意位置调用

if ! command -v python3 >/dev/null 2>&1; then
    echo "错误:未找到 python3。请先安装 Python 3.9+ 并确保其在 PATH 中。" >&2
    exit 1
fi

python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo
echo "✅ 安装完成。运行 ./script/run.sh 启动监控。"