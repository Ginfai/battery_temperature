"""iPhone 电池温度监控入口。"""
import argparse
import logging
import sys
import webbrowser
from pathlib import Path

import uvicorn

from server.app import create_app


def default_out_dir() -> Path:
    """默认导出目录:打包态(__file__ 指向只读 _MEIPASS)落到当前工作目录,源码态放项目根。"""
    if getattr(sys, "frozen", False):
        return Path.cwd() / "exports"
    return Path(__file__).resolve().parent / "exports"


def main() -> None:
    parser = argparse.ArgumentParser(description="iPhone 电池温度实时监控")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 端口（默认 8000）")
    parser.add_argument("--out", type=Path, default=default_out_dir(),
                        help="录制数据输出目录（默认 ./exports）")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--token", default="", help="Android App 数据接入令牌；留空=关闭接入")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = create_app(args.out.resolve(), ingest_token=args.token)
    url = f"http://127.0.0.1:{args.port}"
    print(f"电池温度监控已启动：{url}")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
