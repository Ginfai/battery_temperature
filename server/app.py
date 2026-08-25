"""FastAPI 应用：路由、WebSocket 广播、生命周期管理。"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from server.manager import DeviceManager, NoRecordingError, RecordingActiveError

logger = logging.getLogger(__name__)

_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
STATIC_DIR = _BUNDLE_ROOT / "static"
# 录制导出需用户可写;打包态(_MEIPASS 只读临时目录)下放到当前工作目录,源码态放项目根
EXPORTS_DIR = (_BUNDLE_ROOT if not getattr(sys, "frozen", False)
               else Path.cwd()) / "exports"

BROADCAST_INTERVAL_S = 1.0

# 落盘降采样间隔范围。1s = 原始 1Hz 逐样本落盘(默认),>60s 让 meta.json 崩溃快照过期,
# 约束校验只为暴露这套录制粒度的合理边界。
MIN_INTERVAL_S = 1
MAX_INTERVAL_S = 60


class RecordingStartBody(BaseModel):
    interval_s: float = 1.0


class AndroidSampleBody(BaseModel):
    udid: str                       # Android 侧自生成稳定 ID（如 ANDROID_ID）
    name: str = ""                  # 设备型号（Build.MODEL）
    temperature: int                # BatteryManager EXTRA_TEMPERATURE，0.1°C
    voltage_mv: int = 0
    current_ma: int = 0
    level_percent: int = -1
    is_charging: bool = False


class Broadcaster:
    """向所有接入的 WS 客户端按固定间隔推送快照；发送失败的连接即被移除。"""

    def __init__(self, manager: DeviceManager):
        self.manager = manager
        self.clients: set = set()

    async def run(self) -> None:
        while True:
            if self.clients:
                message = self.manager.snapshot()
                dead = []
                for ws in self.clients:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self.clients.discard(ws)
            await asyncio.sleep(BROADCAST_INTERVAL_S)


def create_app(out_root: Path, ingest_token: str = "") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = DeviceManager(out_root)
        app.state.manager = manager
        app.state.ingest_token = ingest_token
        app.state.broadcaster = Broadcaster(manager)
        broadcaster_task = asyncio.create_task(app.state.broadcaster.run())
        await manager.start()
        logger.info("device manager started")
        yield
        await manager.stop()
        broadcaster_task.cancel()
        logger.info("device manager stopped")

    app = FastAPI(title="iPhone Battery Temperature Monitor", lifespan=lifespan)

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/snapshot")
    async def snapshot():
        return app.state.manager.snapshot()

    @app.get("/api/history/{udid}")
    async def history(udid: str):
        return {"udid": udid, "samples": app.state.manager.history_of(udid)}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        # 接入即推全量快照 + 各设备历史，前端无需等下一个广播周期
        manager = app.state.manager
        snapshot = manager.snapshot()
        histories = {d["udid"]: manager.history_of(d["udid"]) for d in snapshot["devices"]}
        await websocket.send_json({"type": "init", "snapshot": snapshot, "histories": histories})
        app.state.broadcaster.clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()  # 保持连接，忽略客户端消息
        except WebSocketDisconnect:
            pass
        finally:
            app.state.broadcaster.clients.discard(websocket)

    @app.post("/api/recording/start")
    async def recording_start(body: RecordingStartBody):
        if body.interval_s < MIN_INTERVAL_S or body.interval_s > MAX_INTERVAL_S:
            raise HTTPException(status_code=400,
                                detail=f"interval_s 需在 [{MIN_INTERVAL_S}, {MAX_INTERVAL_S}]")
        try:
            return app.state.manager.start_recording(interval_s=body.interval_s)
        except RecordingActiveError:
            raise HTTPException(status_code=409, detail="录制已在进行中")

    @app.post("/api/recording/stop")
    async def recording_stop():
        try:
            return app.state.manager.stop_recording()
        except NoRecordingError:
            raise HTTPException(status_code=409, detail="当前没有进行中的录制")

    @app.post("/api/ingest/android")
    async def ingest_android(body: AndroidSampleBody, token: str = ""):
        """Android App 推送电池样本。token 经 --token 配置；未配置即关闭接入（不裸开）。"""
        if not app.state.ingest_token or token != app.state.ingest_token:
            raise HTTPException(status_code=401, detail="ingest token 无效")
        manager = app.state.manager
        manager.ingest_android_sample(
            udid=body.udid, name=body.name, raw_temperature=body.temperature,
            voltage_mv=body.voltage_mv, current_ma=body.current_ma,
            level_percent=body.level_percent, is_charging=body.is_charging,
        )
        return {"ok": True}

    @app.delete("/api/ingest/android/{udid}")
    async def ingest_android_remove(udid: str, token: str = ""):
        if not app.state.ingest_token or token != app.state.ingest_token:
            raise HTTPException(status_code=401, detail="ingest token 无效")
        if not app.state.manager.remove_android_device(udid):
            raise HTTPException(status_code=404, detail="设备不存在")
        return {"ok": True}

    @app.get("/api/export")
    async def export_list():
        sessions = []
        if EXPORTS_DIR.exists():
            for d in sorted(EXPORTS_DIR.iterdir()):
                if (d / "data.csv").exists():
                    sessions.append({"session": d.name,
                                     "csv": f"/api/export/{d.name}/data.csv",
                                     "meta": f"/api/export/{d.name}/meta.json"})
        return {"sessions": sessions}

    @app.get("/api/export/{session}/{filename}")
    async def export_file(session: str, filename: str):
        if filename not in ("data.csv", "meta.json"):
            raise HTTPException(status_code=404, detail="文件不存在")
        path = EXPORTS_DIR / session / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="会话不存在")
        media_type = "text/csv" if filename.endswith(".csv") else "application/json"
        return FileResponse(path, filename=filename, media_type=media_type)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
