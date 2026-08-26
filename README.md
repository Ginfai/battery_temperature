# 电池温度监控

通过 USB 连接的 iPhone 电池温度实时监控：多设备同屏、温度曲线、录制与导出。

## 运行

**分发给非技术用户:** 见 [`DOCS/SETUP_GUIDE.md`](DOCS/SETUP_GUIDE.md)——一键脚本安装、图文步骤、Windows 需预装 iTunes 的说明。

```bash
pip3 install -r requirements.txt
python3 main.py                # 默认 http://127.0.0.1:8000
python3 main.py --port 9000 --open   # 自定义端口并自动打开浏览器
```

首次连接设备时，iPhone 上会弹出"信任此电脑"对话框，点按"信任"即可。

## Android 手机接入(Wi-Fi)

同一局域网内,Android 手机可把电池数据实时推送到本机显示。启动服务端后,**在监控页点右上角「Android 设备配置」**即可看到服务器地址、端口、接入 Token,在 Android 采集 App 里填入即可连接。`--token` 指定 Android 接入令牌;留空则每次启动自动生成 4 位数字令牌并开启接入。详见 [`DOCS/SETUP_GUIDE.md`](DOCS/SETUP_GUIDE.md)。

## 功能

- **实时监控**：每秒采样一次，显示温度、电压、电流、电量、充电状态；多台设备同屏对比。
- **录制**：点击"开始录制"边采边写盘，崩溃不丢已落盘数据；"停止录制"后生成完整元数据。
- **导出**：页面底部列出所有录制会话，`data.csv` 为数据表，`meta.json` 为机器可读元数据。

## 导出数据格式（面向 AI 分析）

每次录制生成一个目录：

```
exports/<YYYYmmdd-HHMMSS>/
├── data.csv    # 数据行：udid, device_name, timestamp, elapsed_s, temperature_c,
│               #          voltage_mv, current_ma, level_percent, is_charging
└── meta.json   # schema_version、单位声明、设备清单、逐设备统计(min/max/avg/count)
```

- `timestamp`：主机本地时区 ISO8601；`elapsed_s`：相对录制开始的秒数。
- `current_ma` 正值=充电、负值=放电。
- `meta.json` 内含 `description` 与 `units` 字段，AI 可自解释读取，无需额外说明。
- 同一设备相邻行 `elapsed_s` 跳跃 = 该时段设备断开或采样缺失。

## 架构

```
iPhone ──USB──▶ usbmuxd ──▶ lockdown(每设备一条)
                 └─▶ DiagnosticsService.get_battery() 1Hz 轮询
                      └─▶ DeviceCollector(断线分类退避重连)
                           ├─▶ WebSocket 1Hz 快照 ──▶ ECharts 实时曲线
                           └─▶ Recorder(data.csv 逐行 flush + meta.json)
```

| 模块 | 职责 |
|---|---|
| `server/manager.py` | 设备热插拔 watcher、单设备采集任务、温度换算（centi-Celsius → °C） |
| `server/recorder.py` | 录制会话：CSV 增量写、meta.json 整体重写 |
| `server/app.py` | FastAPI 路由、WebSocket 广播 |
| `static/` | 前端：设备卡片 + ECharts 曲线（离线可用） |

数据源为 iOS `diagnostics_relay` 的 IORegistry `IOPMPowerSource`（免越狱），该接口仅请求-响应无推送，轮询是唯一方式。

## 构建二进制(GitHub Actions)

在 GitHub 上打 PyInstaller 产物(Mac + Windows)。有 `.github/workflows/build-release.yml`。

- **手动触发**:仓库 → Actions → "Build binaries" → Run workflow。
- **打 tag**:`git tag v0.1 && git push --tags` 也会自动触发。
- 产物出现在这次 run 的 **Artifacts** 里:`battmon-macos-latest` / `battmon-windows-latest`(每个都是 onedir 目录的 zip)。
- 本机也能直接用 `battmon.spec` 打出同构产物:`pyinstaller battmon.spec`。

> 产物**未签名/未公证**,非开发者分发到他人机子上会遇 macOS 的 Gatekeeper 拦截,需"右键→打开"。Windows 端用户仍需预装 Apple iTunes/驱动才能读 iPhone(见 `DOCS/SETUP_GUIDE.md`)。

## 测试

```bash
python3 -m pytest tests/ -v
```
