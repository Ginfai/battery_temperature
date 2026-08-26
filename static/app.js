/* 前端:WS 接入 + 设备卡片渲染 + ECharts 多设备温度曲线。 */
"use strict";

const WINDOW_MS = 5 * 60 * 1000;  // 曲线窗口约 5 分钟
const STATUS_TEXT = { connecting: "连接中", live: "已连接", unpaired: "待配对", error: "错误" };

const deviceEls = new Map();   // udid -> card element
const seriesData = new Map();  // udid -> [[timestampMs, tempC], ...]
let chart = null;

// ---- WebSocket(带心跳 + 可靠自动重连)----
// 以前:onclose 才重连,WS 被中间设备/系统半挂(能 open 但不再收发)时不会触发 onclose → 页面冻结。
// 现在:HEARTBEAT_MS 无消息即主动断开触发重连;固定 RECONNECT_MS 重连;标签页重新可见时主动重连。
let ws = null;
let heartbeatTimer = null;
let reconnectTimer = null;
const HEARTBEAT_MS = 10000;   // 无消息超时,视为连接半死
const RECONNECT_MS = 3000;    // 断线固定重连间隔

function connect() {
  if (ws) { try { ws.close(); } catch (e) {} }
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => {
    console.log("ws connected");
    clearTimeout(reconnectTimer);
    heartbeat();
  };

  ws.onmessage = (event) => {
    heartbeat();
    const msg = JSON.parse(event.data);
    if (msg.type === "init") {
      for (const [udid, samples] of Object.entries(msg.histories)) {
        seriesData.set(udid, samples.map(s => [Date.parse(s.timestamp), s.temperature_c]));
      }
      render(msg.snapshot);
    } else {
      render(msg);
    }
  };

  ws.onclose = () => {
    stopHeartbeat();
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, RECONNECT_MS);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

// 心跳:连接半死(能 open 但不再收消息)时主动断开,走 onclose 重连
function heartbeat() {
  clearTimeout(heartbeatTimer);
  heartbeatTimer = setTimeout(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.close(); } catch (e) {}
    }
  }, HEARTBEAT_MS);
}
function stopHeartbeat() { clearTimeout(heartbeatTimer); }

// 标签页重新可见时主动重连(浏览器后台会暂挂 WS)
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    stopHeartbeat();
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, RECONNECT_MS);
  }
});

// ---- 渲染 ----
function render(snapshot) {
  document.getElementById("no-device").hidden = snapshot.devices.length > 0;
  // usbmuxd 连不上(Windows 未装 iTunes/驱动)时,给用户更具体的引导
  document.getElementById("no-device").textContent = snapshot.usbmuxd_error
    ? `${snapshot.usbmuxd_error}(macOS 无需;Windows 请安装 Apple iTunes 后重试)`
    : "等待设备连接...(请用 USB 线连接 iPhone)";
  renderDevices(snapshot.devices);
  renderChart(snapshot.devices);
  renderRecording(snapshot.recording);
}

function renderDevices(devices) {
  const container = document.getElementById("devices");
  document.getElementById("no-device").hidden = devices.length > 0;

  const seen = new Set();
  for (const d of devices) {
    seen.add(d.udid);
    let card = deviceEls.get(d.udid);
    if (!card) {
      card = document.createElement("div");
      card.className = "device-card";
      container.appendChild(card);
      deviceEls.set(d.udid, card);
    }
    updateCard(card, d);
  }
  for (const [udid, el] of deviceEls) {
    if (!seen.has(udid)) { el.remove(); deviceEls.delete(udid); seriesData.delete(udid); }
  }
}

function updateCard(card, d) {
  const latest = d.latest;
  const tempHtml = (d.status === "live" && latest)
    ? `${latest.temperature_c.toFixed(2)}<small> °C</small>`
    : "--.--<small> °C</small>";

  let detail = "";
  if (latest && d.status === "live") {
    const currentSign = latest.current_ma >= 0 ? "充电" : "放电";
    detail = `电压 ${latest.voltage_mv} mV · 电流 ${latest.current_ma} mA (${currentSign})<br>` +
             `电量 ${latest.level_percent}% · ${latest.is_charging ? "充电中 ⚡" : "未充电"}`;
  } else if (d.name || d.model_identifier) {
    detail = `${d.model_identifier} · iOS ${d.ios_version}`;
  }

  card.innerHTML =
    `<div><span class="name">${esc(d.name || d.udid)}</span>` +
    `<span class="badge ${d.status}">${STATUS_TEXT[d.status] || d.status}</span></div>` +
    `<div class="udid">${esc(d.udid)}</div>` +
    `<div class="temp">${tempHtml}</div>` +
    `<div class="detail">${detail}</div>` +
    (d.error ? `<div class="err-msg">${esc(d.error)}</div>` : "");
}

// ---- ECharts ----
function initChart() {
  chart = echarts.init(document.getElementById("chart"));
  window.addEventListener("resize", () => chart.resize());
}

function renderChart(devices) {
  const cutoff = Date.now() - WINDOW_MS;
  const series = [];
  const legend = [];
  const liveIds = new Set();

  for (const d of devices) {
    if (d.status !== "live") continue;
    liveIds.add(d.udid);
    let data = seriesData.get(d.udid) || [];
    if (d.latest) {
      const point = [Date.parse(d.latest.timestamp), d.latest.temperature_c];
      const arr = data.length && data[data.length - 1][0] === point[0] ? data : data.concat([point]);
      seriesData.set(d.udid, arr);
      data = arr;
    }
    const trimmed = data.filter(p => p[0] >= cutoff).slice(-600);
    seriesData.set(d.udid, trimmed);
    const label = d.name || d.udid;
    legend.push(label);
    series.push({
      name: label,
      type: "line",
      showSymbol: false,
      data: trimmed,
      lineStyle: { width: 1.5 },
    });
  }

  // 设备断开后其 series 必须显式移除:ECharts merge 模式不会因传入空数组而清掉旧曲线
  for (const udid of [...seriesData.keys()]) {
    if (!liveIds.has(udid)) seriesData.delete(udid);
  }
  chart.setOption({
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: v => v.toFixed(2) + " °C" },
    legend: { data: legend, top: 10 },
    grid: { left: 50, right: 24, top: 40, bottom: 40 },
    xAxis: { type: "time", axisLabel: { formatter: "{HH}:{mm}:{ss}" } },
    yAxis: { type: "value", scale: true, name: "°C" },
    series,
  }, { notMerge: true, lazyUpdate: true });
}

// ---- 录制控制 ----
async function toggleRecording() {
  const recording = await fetchSnapshotRecording();
  try {
    let start;
    if (recording) {
      start = fetch("/api/recording/stop", { method: "POST" });
    } else {
      start = fetch("/api/recording/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval_s: readInterval() }),
      });
    }
    const resp = await start;
    if (!resp.ok) throw new Error((await resp.json()).detail);
    refreshExports();
  } catch (e) {
    setRecordStatus(e.message, true);
  }
}

async function fetchSnapshotRecording() {
  const resp = await fetch("/api/snapshot");
  return (await resp.json()).recording;
}

function readInterval() {
  return parseInt(document.getElementById("record-interval").value, 10);
}

function renderRecording(rec) {
  const btn = document.getElementById("btn-record");
  const status = document.getElementById("record-status");
  if (rec) {
    btn.textContent = "■ 停止录制";
    btn.classList.add("recording");
    sel.disabled = true;
    setRecordStatus(`录制中:${rec.sample_count} 样本 · 间隔 ${rec.interval_s}s · ${formatDuration(rec.duration_s)} · ${rec.dir}`);
  } else {
    btn.textContent = "● 开始录制";
    btn.classList.remove("recording");
    setRecordStatus("");
  }
}

function setRecordStatus(text, isError = false) {
  const status = document.getElementById("record-status");
  status.textContent = text;
  status.classList.toggle("error", isError);
}

async function refreshExports() {
  const resp = await fetch("/api/export");
  const { sessions } = await resp.json();
  const section = document.getElementById("exports-section");
  section.hidden = sessions.length === 0;
  document.getElementById("exports-list").innerHTML = sessions.reverse().map(s =>
    `<li><strong>${esc(s.session)}</strong>` +
    `<span><a href="${s.csv}" download>data.csv</a><a href="${s.meta}" target="_blank">meta.json</a></span></li>`
  ).join("");
}

// ---- 工具 ----
function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60), s = Math.round(seconds % 60);
  return m > 0 ? `${m}m${s}s` : `${s}s`;
}

// ---- 启动 ----
initChart();
document.getElementById("btn-record").addEventListener("click", toggleRecording);
refreshExports();
connect();

// ---- Android 设备接入配置弹窗 ----
function openAndroidConfig() {
  const modal = document.getElementById("android-config-modal");
  modal.style.display = "flex";   // 用内联 display 控制,避免 CSS display:flex 覆盖 hidden
  const body = document.getElementById("android-config-body");
  body.textContent = "加载中...";
  fetch("/api/android-config")
    .then(r => r.json())
    .then(cfg => {
      if (!cfg.enabled) {
        body.innerHTML =
          `<p class="config-warn">未开启 Android 接入。<br>` +
          `请用 <code>--token &lt;值&gt;</code> 启动服务端后重启。</p>`;
        return;
      }
      body.innerHTML =
        `<p>服务器地址(IP)<br><code>${esc(cfg.host)}</code></p>` +
        `<p>端口<br><code>${esc(String(cfg.port))}</code></p>` +
        `<p>接入 Token<br><code>${esc(cfg.token)}</code></p>` +
        `<p class="config-hint">请在 Android App 中填入以上参数后开始采集。</p>`;
    })
    .catch(e => { body.textContent = "获取配置失败: " + e; });
}
function closeAndroidConfig() {
  document.getElementById("android-config-modal").style.display = "none";
}
document.getElementById("btn-android-config").addEventListener("click", openAndroidConfig);
document.getElementById("android-config-close").addEventListener("click", closeAndroidConfig);