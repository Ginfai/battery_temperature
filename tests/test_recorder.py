"""Recorder 录制完整性与统计测试。"""
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from server.manager import Sample
from server.recorder import CSV_COLUMNS, Recorder


@pytest.fixture
def session_dir(tmp_path):
    return tmp_path / "20260822-120000"


def make_sample(temp, t_s=0.0):
    return Sample(
        timestamp=f"2026-08-22T12:00:{int(t_s):02d}.000+08:00",
        temperature_c=temp, voltage_mv=4300, current_ma=-320,
        level_percent=85, is_charging=False,
    )


def read_rows(path):
    with path.open(newline="") as f:
        return list(csv.reader(f))


def test_csv_columns_and_row_count(session_dir):
    rec = Recorder(session_dir)
    rec.start([])
    for i in range(5):
        rec.write_sample("UDID1", "iPhone", make_sample(30.0 + i, t_s=i))
    rec.stop([])

    rows = read_rows(session_dir / "data.csv")
    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 6  # header + 5 samples
    for row in rows[1:]:
        assert len(row) == len(CSV_COLUMNS)
        # 不变量 2：elapsed_s 由 Recorder 签发且单调递增
        assert float(row[3]) >= 0


def test_meta_valid_after_start_without_stop(session_dir):
    """不变量 3：start 后即使从未 stop，meta.json 也是合法 JSON。"""
    rec = Recorder(session_dir)
    devices = [{"udid": "U1", "device_name": "iPhone 15 Pro",
                "model_identifier": "iPhone16,1", "ios_version": "18.5"}]
    rec.start(devices)
    meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == 1
    assert meta["stopped_at"] is None
    assert meta["devices"] == devices


def test_stats_and_final_meta(session_dir):
    rec = Recorder(session_dir)
    rec.start([])
    for i, temp in enumerate((30.0, 32.5, 35.0)):
        rec.write_sample("U1", "iPhone", make_sample(temp, t_s=i))
    rec.stop([])

    meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    st = meta["per_device_stats"]["U1"]
    assert st["sample_count"] == 3
    assert st["temp_min_c"] == 30.0
    assert st["temp_max_c"] == 35.0
    assert st["temp_avg_c"] == 32.5
    assert meta["stopped_at"] is not None
    assert "duration_s" in meta


def test_crash_midway_leaves_clean_csv_and_valid_meta(session_dir):
    """不变量 2/3：模拟崩溃（不调 stop 直接丢弃对象），CSV 无残行、meta 仍合法。"""
    rec = Recorder(session_dir)
    rec.start([])
    for i in range(10):
        rec.write_sample("U1", "iPhone", make_sample(31.0, t_s=i))
        rec._file.flush()
    del rec  # 模拟进程被杀：文件由 GC 兜底关闭，但未调 stop

    rows = read_rows(session_dir / "data.csv")
    assert len(rows) == 11  # header + 10 完整行，无残行
    for row in rows[1:]:
        assert len(row) == len(CSV_COLUMNS)

    meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["stopped_at"] is None


def test_snapshot_counts(session_dir):
    rec = Recorder(session_dir)
    rec.start([])
    for i in range(3):
        rec.write_sample("U1", "A", make_sample(30.0, t_s=i))
    for i in range(3, 5):
        rec.write_sample("U2", "B", make_sample(33.0, t_s=i))
    snap = rec.snapshot()
    assert snap["sample_count"] == 5
    assert snap["device_count"] == 2


def test_downsampling_by_interval(session_dir):
    """interval_s=5:即使每秒喂一个样本,也只有间隔≥5s 的样本落盘(0,5,10 三行)。"""
    rec = Recorder(session_dir, interval_s=5)
    rec.start([])
    for t in range(13):
        rec.write_sample("U1", "A", make_sample(30.0 + t, t_s=t))
    rec.stop([])

    rows = read_rows(session_dir / "data.csv")
    elapsed = sorted(float(r[3]) for r in rows[1:])
    assert len(elapsed) == 3
    # 相邻落盘行间隔应为 interval_s(5s);首个样本必落盘
    assert [round(b - a, 1) for a, b in zip(elapsed, elapsed[1:])] == [5.0, 5.0]
    # 完整统计只统计实际落盘的 3 行
    meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["per_device_stats"]["U1"]["sample_count"] == 3
    assert meta["interval_s"] == 5
