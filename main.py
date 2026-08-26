"""iPhone 电池温度监控入口。"""
import argparse
import logging
import random
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
    # Windows 控制台默认 cp1252,打印中文会 UnicodeEncodeError 直接崩溃;
    # 强制 UTF-8 输出(errors=replace 兜底非 UTF-8 终端)。对 stdout 与 stderr 都生效。
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="iPhone 电池温度实时监控")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 端口(默认 8000)")
    parser.add_argument("--out", type=Path, default=default_out_dir(),
                        help="录制数据输出目录(默认 ./exports)")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--token", default="", help="Android App 数据接入令牌;留空=每次启动自动生成 4 位随机数字")
    parser.add_argument("--mdns", action="store_true",
                        help="发布 _battmon._tcp mDNS 服务供局域网内 Android App 自动发现")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # 未指定 --token 则自动生成 4 位纯数字随机令牌,并自动开启 Android 接入。
    # f"{n:04d}" 保证 0000-9999,避免前导 0 被丢弃(如 037 → 0037)。
    ingest = args.token or f"{random.randint(0, 9999):04d}"
    if ingest:
        print(f"Android 接入令牌(每次启动不同):{ingest}")

    app = create_app(args.out.resolve(), ingest_token=ingest, mdns=args.mdns, port=args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"电池温度监控已启动:{url}")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()