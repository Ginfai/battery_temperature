# iPhone 电池温度监控 · 安装指南

> 这是一个本地工具:把它装在自己电脑上,插上自己的 iPhone,就能实时看到电池温度、录制并导出 CSV 数据。**不上传任何数据,完全离线。**

---

## 0. 你需要什么

| 项目 | 说明 |
|---|---|
| **一台电脑** | macOS 或 Windows |
| **一根数据线** | iPhone 充电线(USB) |
| **一台 iPhone** | iOS 10 以上 |

> **Windows 用户特别注意**:Windows 读取 iPhone 需要 **Apple 官方驱动**。请先安装 **iTunes**(或单独的 Apple Mobile Device 驱动)[从 Apple 官网下载](https://www.apple.com/itunes/download/),否则后面会连不上手机。**macOS 不需要这一步。**

---

## 第一步:安装 Python

> 本工具基于 Python 运行,需要你电脑上先有 Python **3.9 或更高版本**。

<details open>
<summary>macOS</summary>

如果已安装 [Homebrew],运行:

```bash
brew install python@3.12
```

没有 Homebrew 的话,最省事的方式是在终端先执行:

```bash
xcode-select --install
```

然后用下面这条命令验证是否已有 Python:

```bash
python3 --version
```

只要输出 `Python 3.9` 或更高版本的数字(如 `Python 3.12.4`),就可以进入下一步。
</details>

<details>
<summary>Windows</summary>

1. 打开 [python.org/downloads](https://www.python.org/downloads/)
2. 点「Download Python 3.12.x」
3. 运行安装程序时,**务必勾选左下角「Add Python to PATH」** ✅
4. 一路点「Install Now」完成

验证:打开「命令提示符」(按 `Win`+`R`,输入 `cmd` 回车),输入:

```bat
python --version
```

显示 `Python 3.12.x` 即为成功。
</details>

---

## 第二步:装好并启动软件

把整个项目文件夹放到你方便的位置(如 `下载` 或 `桌面`),然后:

### macOS

打开「终端」(Spotlight 搜 `终端`),输入并回车,进入项目目录:

```bash
cd ~/下载/项目文件夹名
```

先装依赖(只需做一次):

```bash
bash script/install.sh
```

启动:

```bash
bash script/run.sh
```

### Windows

进入项目文件夹,双击 **`script/install.bat`**(只需要做一次),等它跑完出现「安装完成」。

再双击 **`script/run.bat`**。

---

无论哪个系统,启动后都会**自动打开浏览器**,出现监控页面:

```
设备卡片
  温度大字   ·  电压/电流/电量/充电状态
实时温度曲线
录制按钮 + 导出列表
```

> 如果浏览器没自动打开,手动访问 `http://127.0.0.1:8000` 即可。

---

## 第三步:连接你的 iPhone

1. 用数据线把 iPhone 插到电脑上。
2. iPhone 上会弹出 **「要信任此电脑吗?」** → 点 **「信任」**,输入锁屏密码。
   (这一步只需第一次做,之后都会自动连接。)
3. 页面上的设备卡片从「等待设备」变成「已连接」,温度实时跳动,曲线开始前进。

> **无线连接**:如果你的 iPhone 之前用过数据线配对,也可以让你的 Mac/PC 与 iPhone 同连一个 Wi-Fi,在 iPhone「设置 → 通用 → 关于本机」里打开「通过 Wi-Fi 连接 iTunes」,之后就能无线读温度,不用一直插线。无线在手机锁屏/省电时可能读取变慢,这是正常的。

---

## 录制与导出

1. 点右上角 **「● 开始录制」**,界面开始计数样本。
2. 想停时点 **「■ 停止录制」**。
3. 页面下方「录制会话」列表出现本次记录,点 **data.csv** 可下载数据表,点 **meta.json** 可查看元数据。

导出的 `data.csv` 每行是一秒一个样本,含 `温度(temperature_c)`、`电压(voltage_mv)`、`电流(current_ma)`、`电量(level_percent)`、`充电状态(is_charging)` 等列,可直接用表格软件或交给脚本/AI 分析。

---

## 常见问题

**启动后提示端口被占用**
可能已有程序占用 8000 端口。改一个端口启动:

`script/run.sh` 里加参数:`./.venv/bin/python main.py --open --port 9000`(Windows 里改 `run.bat` 同理)。

**页面显示「待配对」**
iPhone 没点「信任」,或信任记录被我清过。重新插线,在手机上点「信任」即可。

**Windows 上一直连不上**
多半是没装 iTunes/驱动。回看"你需要什么"一节,装好再试。

---