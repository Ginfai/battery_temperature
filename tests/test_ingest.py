"""Android ingest 采集链路测试：换算、注册、录制挂接、注销。"""
import json
from pathlib import Path

import pytest

from server.manager import DeviceManager, celsius_from_battery_manager


def test_conversion_deci_celsius():
    # BatteryManager EXTRA_TEMPERATURE 单位 0.1°C
    assert celsius_from_battery_manager(327) == 32.7
    assert celsius_from_battery_manager(250) == 25.0


@pytest.fixture
def manager(tmp_path):
    # 不调 start()（无 watcher/采集任务），stop 无事可做，直接丢弃即可
    return DeviceManager(tmp_path)


def _ingest(m, udid="ANDROID-1", temp=327, **kw):
    m.ingest_android_sample(udid, name=kw.pop("name", "Pixel"), raw_temperature=temp, **kw)


def test_ingest_registers_remote_device(manager):
    _ingest(manager)
    snap = manager.snapshot()
    assert len(snap["devices"]) == 1
    d = snap["devices"][0]
    assert d["udid"] == "ANDROID-1"
    assert d["connection_type"] == "Network"
    assert d["status"] == "live"
    assert d["latest"]["temperature_c"] == 32.7


def test_ingest_appends_history_and_updates_latest(manager):
    for t in (320, 327, 330):
        _ingest(manager, temp=t)
    h = manager.history_of("ANDROID-1")
    assert [s["temperature_c"] for s in h] == [32.0, 32.7, 33.0]
    assert manager.remote_collectors["ANDROID-1"].state.latest.temperature_c == 33.0


def test_remove_android_device(manager):
    _ingest(manager)
    assert manager.remove_android_device("ANDROID-1") is True
    assert manager.remove_android_device("ANDROID-1") is False
    assert manager.snapshot()["devices"] == []
    assert manager.history_of("ANDROID-1") == []


def test_recording_includes_remote_samples(manager):
    manager.start_recording(interval_s=1.0)
    _ingest(manager, name="Pixel 8", temp=300)
    _ingest(manager, temp=305)  # 同一设备第二条；interval 降采样由 timestamp 差决定，
    # 但两条 timestamp 均为服务器签发、间隔<1s → 第二条可能被跳过，只断言至少一条落盘
    snap = manager.stop_recording()
    assert snap["sample_count"] >= 1
    meta = json.loads((Path(snap["path"]) / "meta.json").read_text(encoding="utf-8"))
    st = meta["per_device_stats"]["ANDROID-1"]
    assert st["device_name"] == "Pixel 8"


def test_usbmuxd_error_sets_friendly_hint(monkeypatch):
    """usbmuxd 连不上(Windows 未装 iTunes/驱动)时,snapshot 携带友好提示而非让服务崩。"""
    import asyncio
    from unittest.mock import patch

    from server.manager import DeviceManager
    from pymobiledevice3.exceptions import ConnectionFailedToUsbmuxdError

    async def run_once():
        m = DeviceManager("/tmp/nonexistent")
        # 让 _watch_loop 第一次 sleep 就取消,只跑一次对账就返回,避免死循环
        with patch("server.manager.list_devices",
                   side_effect=ConnectionFailedToUsbmuxdError()), \
             patch("server.manager.asyncio.sleep",
                   side_effect=asyncio.CancelledError):
            try:
                await m._watch_loop()
            except asyncio.CancelledError:
                pass  # 单次迭代结束,正常退出
        return m.usbmuxd_error, m.snapshot()["usbmuxd_error"]

    err, snap_err = asyncio.run(run_once())
    assert "iTunes" in err
    assert snap_err == err
