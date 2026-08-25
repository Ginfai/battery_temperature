#!/usr/bin/env bash
# 一键启动:用虚拟环境里的 Python 启动监控服务并自动打开浏览器。
set -euo pipefail
cd "$(dirname "$0")/.."          # 定位到项目根,允许从任意位置调用

if [ ! -x .venv/bin/python ]; then
    echo "错误:未找到虚拟环境。请先运行 ./script/install.sh。" >&2
    exit 1
fi

echo "正在启动 iPhone 电池温度监控 ..."
./.venv/bin/python main.py --open