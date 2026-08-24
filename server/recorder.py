"""录制会话：data.csv 逐行落盘，meta.json 在 start/stop 时整文件重写。"""
import csv
import json
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1

CSV_COLUMNS = ["udid", "device_name", "timestamp", "elapsed_s",
               "temperature_c", "voltage_mv", "current_ma",
               "level_percent", "is_charging"]

META_DESCRIPTION = (
    "iPhone 电池监控录制数据。temperature_c 为电芯温度(°C)；voltage_mv 为电池电压(mV)；"
    "current_ma 为瞬时电流(mA，正值=充电，负值=放电)；level_percent 为电量百分比(0-100)；"
    "timestamp 为主机本地时区 ISO8601 时间；elapsed_s 为相对录制开始的秒数。"
    "同一设备相邻行 elapsed_s 出现跳跃(≳ 采样间隔)表示该时段设备断开、采样缺失,"
    "或该行为按 interval_s 降采样后的落盘行。"
)


class Recorder:
    """一次录制会话：CSV 增量写 + 元数据旁车。

    崩溃安全：每行写入后立即 flush，任意时刻进程被杀 data.csv 不含残行；
    meta.json 在 start 时即为合法完整 JSON（stopped_at=null），stop 时整体重写。
    """

    def __init__(self, out_dir: Path, interval_s: float = 1.0):
        self.dir = out_dir
        self.interval_s = interval_s
        self.started_at = datetime.now().astimezone()
        self.stopped_at = None
        self.error = ""
        self._file = None
        self._writer = None
        self._last_elapsed = None  # 上一落盘样本相对锚点的秒数;None 表示首条必写
        self._elapsed_anchor = None  # 首个样本时间;elapsed_s 相对它签发,保证 >=0 且与点击时刻无关
        # udid -> {"device_name","first_seen","last_seen","sample_count","temp_min_c","temp_max_c","_sum"}
        self._stats = {}

    def start(self, devices_info: list) -> None:
        """建目录、写 CSV 表头与初始 meta.json。devices_info: [{udid, device_name, model_identifier, ios_version}]"""
        self.dir.mkdir(parents=True, exist_ok=True)
        self._file = (self.dir / "data.csv").open("w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(CSV_COLUMNS)
        self._file.flush()
        self._write_meta(devices_info, final=False)

    def write_sample(self, udid: str, device_name: str, sample) -> None:
        sample_time = datetime.fromisoformat(sample.timestamp)
        if self._elapsed_anchor is None:
            self._elapsed_anchor = sample_time
        # elapsed_s 相对首个样本签发;采集层仍 1Hz 喂实时曲线,这里按 interval_s 降采样落盘,
        # "与上一落盘样本间隔 ≥ interval_s" 才写。
        elapsed = (sample_time - self._elapsed_anchor).total_seconds()
        if self._last_elapsed is not None and elapsed - self._last_elapsed < self.interval_s:
            return
        self._last_elapsed = elapsed
        self._writer.writerow([
            udid, device_name, sample.timestamp, f"{elapsed:.3f}",
            sample.temperature_c, sample.voltage_mv, sample.current_ma,
            sample.level_percent, int(sample.is_charging),
        ])
        self._file.flush()
        st = self._stats.setdefault(udid, {
            "device_name": device_name, "first_seen": sample.timestamp,
            "last_seen": sample.timestamp, "sample_count": 0,
            "temp_min_c": None, "temp_max_c": None, "_sum": 0.0})
        st["last_seen"] = sample.timestamp
        st["sample_count"] += 1
        t = sample.temperature_c
        st["temp_min_c"] = t if st["temp_min_c"] is None else min(st["temp_min_c"], t)
        st["temp_max_c"] = t if st["temp_max_c"] is None else max(st["temp_max_c"], t)
        st["_sum"] += t

    def stop(self, devices_info: list, error: str = "") -> None:
        """关闭 CSV 并重写最终 meta.json。devices_info 同 start。"""
        self.error = error
        self.stopped_at = datetime.now().astimezone()
        self._writer = None
        if self._file:
            self._file.close()
            self._file = None
        self._write_meta(devices_info, final=True)

    def snapshot(self) -> dict:
        total = sum(s["sample_count"] for s in self._stats.values())
        duration = ((self.stopped_at or datetime.now().astimezone()) - self.started_at).total_seconds()
        return {
            "dir": self.dir.name,
            "path": str(self.dir),
            "started_at": self.started_at.isoformat(timespec="milliseconds"),
            "duration_s": round(duration, 3),
            "sample_count": total,
            "device_count": len(self._stats),
            "interval_s": self.interval_s,
        }

    def _write_meta(self, devices_info: list, final: bool) -> None:
        stats = {}
        for udid, st in self._stats.items():
            count = st["sample_count"]
            entry = {k: v for k, v in st.items() if k != "_sum"}
            if count:
                entry["temp_avg_c"] = round(st["_sum"] / count, 2)
            stats[udid] = entry

        meta = {
            "schema_version": SCHEMA_VERSION,
            "description": META_DESCRIPTION,
            "interval_s": self.interval_s,
            "started_at": self.started_at.isoformat(timespec="milliseconds"),
            "stopped_at": self.stopped_at.isoformat(timespec="milliseconds") if self.stopped_at else None,
            "error": self.error,
            "columns": list(CSV_COLUMNS),
            "units": {
                "elapsed_s": "seconds since recording start",
                "temperature_c": "degrees Celsius (battery cell)",
                "voltage_mv": "millivolts",
                "current_ma": "milliamperes (positive = charging, negative = discharging)",
                "level_percent": "percent 0-100",
                "is_charging": "boolean as int 0/1",
            },
            "devices": devices_info,
            "per_device_stats": stats,
        }
        if final and self.stopped_at:
            meta["duration_s"] = round((self.stopped_at - self.started_at).total_seconds(), 3)

        # 整体重写：meta.json 不存在中间损坏态
        tmp = self.dir / "meta.json.tmp"
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.dir / "meta.json")
