const cameraBadge = document.getElementById("cameraBadge");
const scaleBadge = document.getElementById("scaleBadge");
const cameraError = document.getElementById("cameraError");
const scaleError = document.getElementById("scaleError");
const weight = document.getElementById("weight");
const rawWeight = document.getElementById("rawWeight");
const tareOffset = document.getElementById("tareOffset");
const updatedAt = document.getElementById("updatedAt");
const tareButton = document.getElementById("tareButton");
const distanceValue = document.getElementById("distanceValue");
const ultrasonicBadge = document.getElementById("ultrasonicBadge");
const ultrasonicError = document.getElementById("ultrasonicError");
const distanceUpdatedAt = document.getElementById("distanceUpdatedAt");
const bufferStatus = document.getElementById("bufferStatus");
const lastVideoPath = document.getElementById("lastVideoPath");
const telegramStatus = document.getElementById("telegramStatus");
const distanceThresholdStatus = document.getElementById("distanceThresholdStatus");
const monitorBadge = document.getElementById("monitorBadge");
const baselineStatus = document.getElementById("baselineStatus");
const stageStatus = document.getElementById("stageStatus");
const measureButton = document.getElementById("measureButton");
const armButton = document.getElementById("armButton");
const resetAlarmButton = document.getElementById("resetAlarmButton");
const alarmModal = document.getElementById("alarmModal");
const alarmMessage = document.getElementById("alarmMessage");
const alarmCloseButton = document.getElementById("alarmCloseButton");
const weightRate = document.getElementById("weightRate");
const distanceThreshold = document.getElementById("distanceThreshold");

let alarmShownAt = "";
let settingsTimer = null;

function setBadge(el, ok) {
  el.textContent = ok ? "ON" : "OFF";
  el.className = ok ? "badge ok" : "badge bad";
}

function setMonitorBadge(data) {
  if (data.alarm_active) {
    monitorBadge.textContent = "ALARM";
    monitorBadge.className = "badge bad";
    return;
  }
  if (data.camera_requested || data.monitor_stage === "camera_ready") {
    monitorBadge.textContent = "CAMERA";
    monitorBadge.className = "badge ok";
    return;
  }
  if (data.monitor_armed) {
    monitorBadge.textContent = "ARMED";
    monitorBadge.className = "badge ok";
    return;
  }
  monitorBadge.textContent = "IDLE";
  monitorBadge.className = "badge";
}

function showAlarm(data) {
  if (!data.alarm_active || data.alarm_at === alarmShownAt) return;
  alarmShownAt = data.alarm_at;
  alarmMessage.textContent = data.alarm_message || "로드셀 변화가 감지되었습니다.";
  alarmModal.classList.add("open");
  window.alert(alarmMessage.textContent);
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    const data = await res.json();
    setBadge(cameraBadge, data.camera_ok);
    setBadge(scaleBadge, data.scale_ok);
    setBadge(ultrasonicBadge, data.ultrasonic_ok);
    setMonitorBadge(data);
    cameraError.textContent = data.camera_ok ? "" : data.camera_error;
    cameraError.style.display = data.camera_ok ? "none" : "grid";
    scaleError.textContent = data.scale_ok ? "" : data.scale_error;
    ultrasonicError.textContent = data.ultrasonic_ok ? "" : data.ultrasonic_error;
    weight.textContent = Number(data.weight_g || 0).toFixed(1);
    rawWeight.textContent = Number(data.raw_weight || 0).toFixed(0);
    tareOffset.textContent = Number(data.tare_offset || 0).toFixed(0);
    updatedAt.textContent = data.last_weight_at || "-";
    distanceValue.textContent = Number(data.distance_cm || 0).toFixed(1);
    distanceUpdatedAt.textContent = data.last_distance_at || "-";
    bufferStatus.textContent =
      `${Number(data.camera_buffer_seconds || 0).toFixed(1)}s / ${data.camera_buffer_frames || 0} frames`;
    distanceThresholdStatus.textContent =
      `${Number(data.ultrasonic_camera_threshold_cm || 0).toFixed(1)}cm 이하`;
    lastVideoPath.textContent = data.last_video_path || "-";
    telegramStatus.textContent = data.telegram_error
      ? data.telegram_error
      : (data.last_telegram_at ? `sent ${data.last_telegram_at}` : "not sent");
    baselineStatus.textContent =
      `${Number(data.baseline_weight_g || 0).toFixed(1)}g`;
    stageStatus.textContent = data.video_saving
      ? `${data.monitor_stage || "idle"} / saving`
      : data.monitor_stage || "idle";
    const weightRateStatus = document.getElementById("weightRateStatus");
    if (weightRateStatus) {
      weightRateStatus.textContent =
        `${Number(data.weight_rate_gps || 0).toFixed(1)}g/s / ${Number(data.weight_rate_threshold_gps || 0).toFixed(1)}g/s`;
    }
    showAlarm(data);
  } catch (err) {
    setBadge(cameraBadge, false);
    setBadge(scaleBadge, false);
    setBadge(ultrasonicBadge, false);
    scaleError.textContent = `상태 API 연결 실패: ${err}`;
  }
}

async function tare() {
  tareButton.disabled = true;
  try {
    await fetch("/api/tare", { method: "POST" });
    await refreshStatus();
  } finally {
    tareButton.disabled = false;
  }
}

async function postJson(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function measureBaseline() {
  measureButton.disabled = true;
  try {
    await postJson("/api/measure");
    await refreshStatus();
  } finally {
    measureButton.disabled = false;
  }
}

async function armMonitor() {
  armButton.disabled = true;
  try {
    await postJson("/api/monitor", {
      weight_rate_threshold_gps: Number(weightRate.value || 0),
      ultrasonic_camera_threshold_cm: Number(distanceThreshold.value || 0),
    });
    await refreshStatus();
  } finally {
    armButton.disabled = false;
  }
}

function scheduleApplySettings() {
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(() => {
    armMonitor();
  }, 400);
}

async function resetMonitor() {
  await postJson("/api/reset");
  alarmModal.classList.remove("open");
  alarmShownAt = "";
  await refreshStatus();
}

tareButton.addEventListener("click", tare);
measureButton.addEventListener("click", measureBaseline);
armButton.addEventListener("click", armMonitor);
weightRate.addEventListener("change", scheduleApplySettings);
weightRate.addEventListener("input", scheduleApplySettings);
distanceThreshold.addEventListener("change", scheduleApplySettings);
distanceThreshold.addEventListener("input", scheduleApplySettings);
resetAlarmButton.addEventListener("click", resetMonitor);
alarmCloseButton.addEventListener("click", resetMonitor);
refreshStatus();
armMonitor();
setInterval(refreshStatus, 500);
