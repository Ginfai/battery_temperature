"""设备发现、采集与状态聚合。"""
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from pymobiledevice3.exceptions import NotPairedError, PairingError
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.diagnostics import DiagnosticsService
from pymobiledevice3.usbmux import list_devices

from server.recorder import Recorder

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0
WATCH_INTERVAL_S = 3.0
RECONNECT_INTERVAL_S = 5.0
PAIR_RETRY_INTERVAL_S = 30.0  # 未配对退避，避免连续弹出信任对话框
HISTORY_MAXLEN = 3600         # 1Hz 下约 1 小时回看


class RecordingActiveError(Exception):
    pass


class NoRecordingError(Exception):
    pass


def celsius_from_ioregistry(raw_temperature) -> float:
    """IORegistry 电池温度单位为 centi-摄氏度（°C×100），实测 3219 → 32.19°C。全项目唯一换算点。"""
    return round(raw_temperature / 100, 2)


@dataclass
class Sample:
    timestamp: str
    temperature_c: float
    voltage_mv: int
    current_ma: int
    level_percent: int
    is_charging: bool


@dataclass
class DeviceState:
    udid: str
    name: str = ""
    model_identifier: str = ""   # 如 iPhone16,1
    ios_version: str = ""
    connection_type: str = ""
    status: str = "connecting"   # connecting | live | unpaired | error
    error: str = ""
    latest: Optional[Sample] = None
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_MAXLEN))


class DeviceCollector:
    """单设备采集任务：建立连接、按固定间隔轮询电池数据、故障分类退避重试。

    传输层异常类型随库内部实现变化（MuxException/OSError/ConnectionTerminatedError…），
    故监督循环捕获 Exception 分类退避——这是本模块的核心功能而非防御性装饰。
    """

    def __init__(self, udid: str, manager: "DeviceManager"):
        self.udid = udid
        self.manager = manager
        self.state = DeviceState(udid=udid)
        self.task: Optional[asyncio.Task] = None

    async def run(self) -> None:
        while True:
            diagnostics = None
            try:
                lockdown = await create_using_usbmux(serial=self.udid, autopair=True, pair_timeout=30)
                self._fill_device_info(lockdown)
                diagnostics = DiagnosticsService(lockdown=lockdown)
                self.state.status = "live"
                self.state.error = ""
                while True:
                    await self._poll_once(diagnostics)
                    await asyncio.sleep(POLL_INTERVAL_S)
            except (NotPairedError, PairingError):
                self.state.status = "unpaired"
                self.state.error = "设备未配对：请在 iPhone 上点按“信任此电脑”"
                await asyncio.sleep(PAIR_RETRY_INTERVAL_S)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state.status = "error"
                self.state.error = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(RECONNECT_INTERVAL_S)
            finally:
                if diagnostics is not None:
                    await diagnostics.close()

    def _fill_device_info(self, lockdown) -> None:
        values = lockdown.all_values
        self.state.name = values.get("DeviceName") or ""
        self.state.model_identifier = lockdown.product_type or ""
        self.state.ios_version = lockdown.product_version or ""
        if lockdown.service is not None and lockdown.service.mux_device is not None:
            self.state.connection_type = lockdown.service.mux_device.connection_type or ""

    async def _poll_once(self, diagnostics: DiagnosticsService) -> None:
        raw = await diagnostics.get_battery()
        if raw is None or raw.get("Temperature") is None:
            return  # 本次无有效样本
        sample = Sample(
            timestamp=datetime.now().astimezone().isoformat(timespec="milliseconds"),
            temperature_c=celsius_from_ioregistry(raw["Temperature"]),
            voltage_mv=int(raw.get("Voltage") or 0),
            current_ma=int(raw.get("InstantAmperage") or 0),
            level_percent=int(raw.get("CurrentCapacity") or 0),
            is_charging=bool(raw.get("IsCharging")),
        )
        self.state.latest = sample
        self.state.history.append(sample)
        self.manager.on_sample(self.udid, sample)


class DeviceManager:
    """watcher 对照 usbmuxd 设备清单启停 collector；对外提供快照与录制挂接。

    单事件循环内运行：共享状态的读-改-写序列均不跨 await（collectors 增删除外，由 _lock 保护）。
    """

    def __init__(self, out_root: Path):
        self.out_root = out_root
        self.collectors: dict = {}
        self.recorder = None  # Recorder | None
        self._lock = asyncio.Lock()
        self._watch_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        if self.recorder is not None:
            self.stop_recording()
        async with self._lock:
            for collector in self.collectors.values():
                if collector.task:
                    collector.task.cancel()
            self.collectors.clear()
        if self._watch_task:
            self._watch_task.cancel()

    async def _watch_loop(self) -> None:
        while True:
            try:
                devices = await list_devices()
                udids = {d.serial for d in devices}
                async with self._lock:
                    for udid in udids - self.collectors.keys():
                        collector = DeviceCollector(udid, self)
                        collector.task = asyncio.create_task(collector.run())
                        self.collectors[udid] = collector
                    for udid in self.collectors.keys() - udids:
                        collector = self.collectors.pop(udid)
                        if collector.task:
                            collector.task.cancel()
            except Exception:
                logger.exception("device watch failed")
            await asyncio.sleep(WATCH_INTERVAL_S)

    def on_sample(self, udid: str, sample: Sample) -> None:
        """collector 同步回调：挂接录制。读-改-写内不跨 await。"""
        if self.recorder is None:
            return
        state = self.collectors[udid].state  # collectors 存 DeviceCollector，设备信息在 .state 上
        try:
            self.recorder.write_sample(udid, state.name, sample)
        except OSError as exc:
            # 文件系统边界故障（磁盘满等）：显式终止录制并标记，绝不静默吞掉
            logger.exception("recording write failed")
            self.stop_recording(error=f"录制写入失败: {exc}")

    def snapshot(self) -> dict:
        # 显式构造：vars(DeviceState) 会带出 history(deque) 与 latest(未展平的 Sample)，
        # 两者都不是 JSON 原生类型，直接 vars 会让 WS 序列化崩溃
        devices = [
            {
                "udid": s.udid,
                "name": s.name,
                "model_identifier": s.model_identifier,
                "ios_version": s.ios_version,
                "connection_type": s.connection_type,
                "status": s.status,
                "error": s.error,
                "latest": vars(s.latest) if s.latest else None,
            }
            for s in (c.state for c in self.collectors.values())
        ]
        return {
            "devices": devices,
            "recording": self.recorder.snapshot() if self.recorder else None,
        }

    def history_of(self, udid: str) -> list:
        collector = self.collectors.get(udid)
        return [vars(s) for s in collector.state.history] if collector else []

    def start_recording(self, interval_s: float = 1.0) -> dict:
        if self.recorder is not None:
            raise RecordingActiveError()
        session_dir = self.out_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.recorder = Recorder(session_dir, interval_s=interval_s)
        live_states = [c.state for c in self.collectors.values()]
        self.recorder.start([self._device_info(s) for s in live_states])
        logger.info("recording started: %s", session_dir)
        return self.recorder.snapshot()

    def stop_recording(self, error: str = "") -> dict:
        if self.recorder is None:
            raise NoRecordingError()
        recorder, self.recorder = self.recorder, None
        states = [c.state for c in self.collectors.values()]
        recorder.stop([self._device_info(s) for s in states], error=error)
        logger.info("recording stopped: %s", recorder.dir)
        return recorder.snapshot()

    @staticmethod
    def _device_info(state: DeviceState) -> dict:
        return {
            "udid": state.udid,
            "device_name": state.name,
            "model_identifier": state.model_identifier,
            "ios_version": state.ios_version,
            "status": state.status,
        }
