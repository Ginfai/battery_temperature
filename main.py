"""iPhone 电池温度监控入口。"""
import argparse
import logging
import webbrowser
from pathlib import Path

import uvicorn

from server.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="iPhone 电池温度实时监控")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 端口（默认 8000）")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "exports",
                        help="录制数据输出目录（默认 ./exports）")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = create_app(args.out.resolve())
    url = f"http://127.0.0.1:{args.port}"
    print(f"电池温度监控已启动：{url}")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
