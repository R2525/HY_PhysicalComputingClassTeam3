from __future__ import annotations

import os
import socket
import threading
import time
import atexit
import json
import mimetypes
import uuid
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Generator
from urllib import request as urlrequest
from urllib.error import HTTPError
from urllib.parse import urlencode

from flask import Flask, Response, jsonify, render_template_string


BASE_DIR = Path(__file__).resolve().parent
PIN_DOC = BASE_DIR / "fils" / "pin.md"

HX711_DOUT_PIN = int(os.getenv("HX711_DOUT_PIN", "29"))
HX711_SCK_PIN = int(os.getenv("HX711_SCK_PIN", "31"))
HX711_PIN_MODE = os.getenv("HX711_PIN_MODE", "BOARD").upper()
HX711_OFFSET = float(os.getenv("HX711_OFFSET", "0"))
HX711_SCALE = float(os.getenv("HX711_SCALE", "1"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
ULTRASONIC_TRIG_PIN = int(os.getenv("ULTRASONIC_TRIG_PIN", "16"))
ULTRASONIC_ECHO_PIN = int(os.getenv("ULTRASONIC_ECHO_PIN", "18"))
ULTRASONIC_PIN_MODE = os.getenv("ULTRASONIC_PIN_MODE", "BOARD").upper()
SAMPLE_INTERVAL_SECONDS = float(os.getenv("SAMPLE_INTERVAL_SECONDS", "0.25"))
CAMERA_BUFFER_SECONDS = float(os.getenv("CAMERA_BUFFER_SECONDS", "30"))
POST_EVENT_SECONDS = float(os.getenv("POST_EVENT_SECONDS", "10"))
CAMERA_FPS = float(os.getenv("CAMERA_FPS", "20"))
ULTRASONIC_CAMERA_THRESHOLD_CM = float(os.getenv("ULTRASONIC_CAMERA_THRESHOLD_CM", "50"))
EVENT_VIDEO_DIR = Path(os.getenv(
    "EVENT_VIDEO_DIR",
    "/home/phc_13/Projects3/smartDeliveryContainer/video",
))
WEIGHT_EVENT_COOLDOWN_SECONDS = float(os.getenv("WEIGHT_EVENT_COOLDOWN_SECONDS", "12"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BCM_TO_BOARD = {
    2: 3,
    3: 5,
    4: 7,
    17: 11,
    27: 13,
    22: 15,
    10: 19,
    9: 21,
    11: 23,
    5: 29,
    6: 31,
    13: 33,
    19: 35,
    26: 37,
    14: 8,
    15: 10,
    18: 12,
    23: 16,
    24: 18,
    25: 22,
    8: 24,
    7: 26,
    12: 32,
    16: 36,
    20: 38,
    21: 40,
}
BOARD_TO_BCM = {board: bcm for bcm, board in BCM_TO_BOARD.items()}


def effective_gpio_pin(pin: int, pin_mode: str) -> int:
    if pin_mode == HX711_PIN_MODE:
        return pin
    if pin_mode == "BCM" and HX711_PIN_MODE == "BOARD":
        return BCM_TO_BOARD.get(pin, pin)
    if pin_mode == "BOARD" and HX711_PIN_MODE == "BCM":
        return BOARD_TO_BCM.get(pin, pin)
    return pin


def telegram_enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def telegram_post_form(method: str, data: dict[str, str]) -> None:
    if not telegram_enabled():
        state.telegram_ok = False
        state.telegram_error = "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다"
        return

    encoded = urlencode(data).encode("utf-8")
    req = urlrequest.Request(telegram_api_url(method), data=encoded, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    if not payload.get("ok"):
        raise RuntimeError(str(payload))
    state.telegram_ok = True
    state.telegram_error = ""
    state.last_telegram_at = datetime.now().isoformat(timespec="seconds")


def telegram_send_message(text: str) -> None:
    try:
        telegram_post_form("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as exc:
        state.telegram_ok = False
        state.telegram_error = f"텔레그램 메시지 전송 실패: {exc}"


def telegram_send_video(path: Path, caption: str) -> None:
    if not telegram_enabled():
        state.telegram_ok = False
        state.telegram_error = "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다"
        return

    try:
        boundary = f"----filmover-{uuid.uuid4().hex}"
        mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
        head = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{TELEGRAM_CHAT_ID}\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="video"; filename="{path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = head + path.read_bytes() + tail
        req = urlrequest.Request(
            telegram_api_url("sendVideo"),
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urlrequest.urlopen(req, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        if not payload.get("ok"):
            raise RuntimeError(str(payload))
        state.telegram_ok = True
        state.telegram_error = ""
        state.last_telegram_at = datetime.now().isoformat(timespec="seconds")
    except Exception as exc:
        state.telegram_ok = False
        state.telegram_error = f"텔레그램 영상 전송 실패: {exc}"


@dataclass
class DeviceState:
    weight_g: float = 0.0
    raw_weight: float = 0.0
    tare_offset: float = 0.0
    distance_cm: float = 0.0
    ultrasonic_ok: bool = False
    ultrasonic_error: str = ""
    camera_ok: bool = False
    camera_error: str = ""
    camera_requested: bool = False
    camera_buffer_seconds: float = 0.0
    camera_buffer_frames: int = 0
    video_saving: bool = False
    last_video_path: str = ""
    last_video_at: str = ""
    scale_ok: bool = False
    scale_error: str = ""
    last_weight_at: str = ""
    last_distance_at: str = ""
    monitor_armed: bool = True
    monitor_stage: str = "armed"
    ultrasonic_camera_threshold_cm: float = ULTRASONIC_CAMERA_THRESHOLD_CM
    weight_delta_threshold_g: float = 10000.0
    weight_rate_gps: float = 0.0
    weight_rate_threshold_gps: float = 10000.0
    baseline_weight_g: float = 0.0
    last_event_weight_g: float = 0.0
    alarm_active: bool = False
    alarm_message: str = ""
    alarm_at: str = ""
    telegram_ok: bool = False
    telegram_error: str = ""
    last_telegram_at: str = ""
    started_at: str = datetime.now().isoformat(timespec="seconds")


class LoadCellReader:
    def __init__(self) -> None:
        self._gpio = None
        self.error = ""

    def open(self) -> bool:
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]

            GPIO.setwarnings(False)
            if HX711_PIN_MODE == "BOARD":
                GPIO.setmode(GPIO.BOARD)
            elif HX711_PIN_MODE == "BCM":
                GPIO.setmode(GPIO.BCM)
            else:
                self.error = f"지원하지 않는 HX711_PIN_MODE: {HX711_PIN_MODE}"
                return False

            GPIO.setup(HX711_DOUT_PIN, GPIO.IN)
            GPIO.setup(HX711_SCK_PIN, GPIO.OUT)
            GPIO.output(HX711_SCK_PIN, False)
            self._gpio = GPIO
            return True
        except Exception as exc:
            self.error = f"HX711 초기화 실패: {exc}"
            self._gpio = None
            return False

    def close(self) -> None:
        if self._gpio is not None:
            self._gpio.cleanup()

    def _read_raw_once(self) -> int:
        if self._gpio is None:
            raise RuntimeError(self.error or "HX711이 열려 있지 않습니다")

        deadline = time.monotonic() + 1.0
        while self._gpio.input(HX711_DOUT_PIN) == 1:
            if time.monotonic() > deadline:
                raise RuntimeError("HX711 준비 대기 시간 초과")
            time.sleep(0.001)

        value = 0
        for _ in range(24):
            self._gpio.output(HX711_SCK_PIN, True)
            value = (value << 1) | int(self._gpio.input(HX711_DOUT_PIN))
            self._gpio.output(HX711_SCK_PIN, False)

        self._gpio.output(HX711_SCK_PIN, True)
        self._gpio.output(HX711_SCK_PIN, False)

        if value & 0x800000:
            value -= 0x1000000
        return value

    def read(self) -> tuple[float, float]:
        readings = [self._read_raw_once() for _ in range(5)]
        raw = sum(readings) / len(readings)
        raw_f = float(raw)
        grams = (raw_f - HX711_OFFSET - state.tare_offset) / HX711_SCALE
        return raw_f, grams


class UltrasonicReader:
    def __init__(self) -> None:
        self._gpio = None
        self.error = ""

    def open(self) -> bool:
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]

            GPIO.setwarnings(False)
            if HX711_PIN_MODE == "BOARD":
                GPIO.setmode(GPIO.BOARD)
            elif HX711_PIN_MODE == "BCM":
                GPIO.setmode(GPIO.BCM)
            else:
                self.error = f"지원하지 않는 HX711_PIN_MODE: {HX711_PIN_MODE}"
                return False

            GPIO.setup(effective_gpio_pin(ULTRASONIC_TRIG_PIN, ULTRASONIC_PIN_MODE), GPIO.OUT)
            GPIO.setup(effective_gpio_pin(ULTRASONIC_ECHO_PIN, ULTRASONIC_PIN_MODE), GPIO.IN)
            GPIO.output(effective_gpio_pin(ULTRASONIC_TRIG_PIN, ULTRASONIC_PIN_MODE), False)
            self._gpio = GPIO
            return True
        except Exception as exc:
            self.error = f"초음파 센서 초기화 실패: {exc}"
            self._gpio = None
            return False

    def read_cm(self) -> float:
        if self._gpio is None:
            raise RuntimeError(self.error or "초음파 센서가 열려 있지 않습니다")

        trig = effective_gpio_pin(ULTRASONIC_TRIG_PIN, ULTRASONIC_PIN_MODE)
        echo = effective_gpio_pin(ULTRASONIC_ECHO_PIN, ULTRASONIC_PIN_MODE)

        self._gpio.output(trig, False)
        time.sleep(0.00002)
        self._gpio.output(trig, True)
        time.sleep(0.00001)
        self._gpio.output(trig, False)

        deadline = time.monotonic() + 0.04
        while self._gpio.input(echo) == 0:
            if time.monotonic() > deadline:
                raise RuntimeError("초음파 echo 시작 대기 시간 초과")
        pulse_start = time.monotonic()

        deadline = pulse_start + 0.04
        while self._gpio.input(echo) == 1:
            if time.monotonic() > deadline:
                raise RuntimeError("초음파 echo 종료 대기 시간 초과")
        pulse_end = time.monotonic()

        return (pulse_end - pulse_start) * 34300 / 2


class CameraStream:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cap = None
        self._last_jpeg: bytes | None = None
        self._buffer: deque[tuple[float, bytes]] = deque()
        self._last_frame_size: tuple[int, int] | None = None
        self.error = ""

    def open(self) -> bool:
        if self._cap is not None:
            return True
        try:
            import cv2  # type: ignore[import]

            cap = cv2.VideoCapture(CAMERA_INDEX)
            if not cap.isOpened():
                self.error = f"USB 카메라를 열 수 없습니다: index {CAMERA_INDEX}"
                return False
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
            self._cap = cap
            return True
        except Exception as exc:
            self.error = f"카메라 초기화 실패: {exc}"
            self._cap = None
            return False

    def read_loop(self, state: DeviceState) -> None:
        try:
            import cv2  # type: ignore[import]
        except Exception as exc:
            state.camera_error = f"opencv-python import 실패: {exc}"
            return

        while True:
            if not state.camera_requested and not state.video_saving:
                if self._cap is not None:
                    self.close()
                with self._lock:
                    self._last_jpeg = None
                    self._buffer.clear()
                state.camera_ok = False
                state.camera_buffer_frames = 0
                state.camera_buffer_seconds = 0.0
                state.camera_error = "초음파 기준 대기 중"
                time.sleep(0.25)
                continue

            if self._cap is None:
                if not self.open():
                    state.camera_ok = False
                    state.camera_error = self.error or "카메라가 열려 있지 않습니다"
                    time.sleep(1)
                    continue

            ok, frame = self._cap.read()
            if not ok:
                state.camera_ok = False
                state.camera_error = "카메라 프레임 읽기 실패"
                time.sleep(0.25)
                continue

            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if ok:
                now = time.monotonic()
                with self._lock:
                    jpeg = encoded.tobytes()
                    self._last_jpeg = jpeg
                    self._last_frame_size = (frame.shape[1], frame.shape[0])
                    self._buffer.append((now, jpeg))
                    cutoff = now - CAMERA_BUFFER_SECONDS
                    while self._buffer and self._buffer[0][0] < cutoff:
                        self._buffer.popleft()
                    state.camera_buffer_frames = len(self._buffer)
                    if self._buffer:
                        state.camera_buffer_seconds = self._buffer[-1][0] - self._buffer[0][0]
                state.camera_ok = True
                state.camera_error = ""
            time.sleep(max(0.0, (1 / CAMERA_FPS) - 0.005))

    def save_event_clip(self, event_time: float, event_id: str) -> None:
        if state.video_saving:
            return
        state.camera_requested = True
        threading.Thread(target=self._save_event_clip, args=(event_time, event_id), daemon=True).start()

    def _save_event_clip(self, event_time: float, event_id: str) -> None:
        state.video_saving = True
        try:
            import cv2  # type: ignore[import]
            import numpy as np  # type: ignore[import]

            EVENT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
            end_time = event_time + POST_EVENT_SECONDS
            frames: list[tuple[float, bytes]] = []
            seen: set[float] = set()

            while time.monotonic() <= end_time:
                with self._lock:
                    current = [
                        item for item in self._buffer
                        if event_time - CAMERA_BUFFER_SECONDS <= item[0] <= time.monotonic()
                    ]
                for ts, jpeg in current:
                    if ts not in seen:
                        frames.append((ts, jpeg))
                        seen.add(ts)
                time.sleep(0.1)

            frames.sort(key=lambda item: item[0])
            if not frames:
                state.camera_requested = True
                retry_deadline = time.monotonic() + 2
                while time.monotonic() < retry_deadline and not frames:
                    with self._lock:
                        frames = list(self._buffer)
                    time.sleep(0.1)
                frames.sort(key=lambda item: item[0])
            if not frames:
                raise RuntimeError("저장할 카메라 프레임이 없습니다")

            first = cv2.imdecode(np.frombuffer(frames[0][1], dtype=np.uint8), cv2.IMREAD_COLOR)
            if first is None:
                raise RuntimeError("첫 프레임 디코딩 실패")
            h, w = first.shape[:2]
            path = EVENT_VIDEO_DIR / f"loadcell_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{event_id}.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), CAMERA_FPS, (w, h))
            for _, jpeg in frames:
                frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, (w, h))
                writer.write(frame)
            writer.release()
            state.last_video_path = str(path)
            state.last_video_at = datetime.now().isoformat(timespec="seconds")
            telegram_send_video(
                path,
                (
                    "필름오버 이벤트 영상\n"
                    f"저장 시각: {state.last_video_at}\n"
                    f"현재 무게: {state.weight_g:.1f}g\n"
                    f"변화율: {state.weight_rate_gps:.1f}g/s\n"
                    f"초음파 거리: {state.distance_cm:.1f}cm"
                ),
            )
        except Exception as exc:
            state.camera_error = f"이벤트 영상 저장 실패: {exc}"
        finally:
            state.video_saving = False
            if state.monitor_stage == "saving":
                state.monitor_stage = "camera_ready" if state.camera_requested else "armed"

    def frames(self) -> Generator[bytes, None, None]:
        while True:
            with self._lock:
                frame = self._last_jpeg
            if frame is None:
                time.sleep(0.2)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.04)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


app = Flask(__name__)
state = DeviceState()
load_cell = LoadCellReader()
ultrasonic = UltrasonicReader()
camera = CameraStream()
atexit.register(load_cell.close)
atexit.register(camera.close)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def weight_loop() -> None:
    if not load_cell.open():
        state.scale_ok = False
        state.scale_error = load_cell.error
        return

    previous_weight: float | None = None
    previous_at = time.monotonic()

    while True:
        try:
            raw, grams = load_cell.read()
            now_monotonic = time.monotonic()
            state.raw_weight = raw
            state.weight_g = grams
            if previous_weight is not None:
                elapsed = max(now_monotonic - previous_at, 0.001)
                state.weight_rate_gps = (grams - previous_weight) / elapsed
            previous_weight = grams
            previous_at = now_monotonic
            if not getattr(weight_loop, "_baseline_set", False):
                state.baseline_weight_g = grams
                setattr(weight_loop, "_baseline_set", True)
            state.last_weight_at = datetime.now().isoformat(timespec="seconds")
            state.scale_ok = True
            state.scale_error = ""
            monitor_tick()
        except Exception as exc:
            state.scale_ok = False
            state.scale_error = str(exc)
        time.sleep(SAMPLE_INTERVAL_SECONDS)


def monitor_tick() -> None:
    if not state.monitor_armed:
        return

    now = time.monotonic()
    rate = abs(state.weight_rate_gps)
    if rate < state.weight_rate_threshold_gps or state.video_saving:
        if state.monitor_stage not in {"camera_ready", "saving"}:
            state.monitor_stage = "armed"
        return

    if getattr(monitor_tick, "_last_event_at", 0.0) + WEIGHT_EVENT_COOLDOWN_SECONDS > now:
        return
    setattr(monitor_tick, "_last_event_at", now)

    event_id = datetime.now().strftime("%Y%m%d%H%M%S")
    state.last_event_weight_g = state.weight_g
    state.alarm_active = True
    state.monitor_stage = "saving"
    state.alarm_at = datetime.now().isoformat(timespec="seconds")
    state.alarm_message = (
        f"로드셀 변화율 {rate:.1f}g/s 감지. "
        f"최근 {CAMERA_BUFFER_SECONDS:.0f}초 + 이후 {POST_EVENT_SECONDS:.0f}초 영상을 저장합니다."
    )
    telegram_send_message(
        "필름오버 로드셀 이벤트 감지\n"
        f"감지 시각: {state.alarm_at}\n"
        f"현재 무게: {state.weight_g:.1f}g\n"
        f"변화율: {rate:.1f}g/s\n"
        f"초음파 거리: {state.distance_cm:.1f}cm\n"
        f"영상 저장: 이전 최대 {CAMERA_BUFFER_SECONDS:.0f}초 + 이후 {POST_EVENT_SECONDS:.0f}초"
    )
    camera.save_event_clip(now, event_id)
    state.baseline_weight_g = state.weight_g


def ultrasonic_loop() -> None:
    if not ultrasonic.open():
        state.ultrasonic_ok = False
        state.ultrasonic_error = ultrasonic.error
        return

    while True:
        try:
            state.distance_cm = ultrasonic.read_cm()
            state.last_distance_at = datetime.now().isoformat(timespec="seconds")
            state.ultrasonic_ok = True
            state.ultrasonic_error = ""
            if 0 < state.distance_cm <= state.ultrasonic_camera_threshold_cm:
                state.camera_requested = True
                if state.monitor_stage == "armed":
                    state.monitor_stage = "camera_ready"
            elif not state.video_saving:
                state.camera_requested = False
                if state.monitor_stage == "camera_ready":
                    state.monitor_stage = "armed"
        except Exception as exc:
            state.ultrasonic_ok = False
            state.ultrasonic_error = str(exc)
        time.sleep(SAMPLE_INTERVAL_SECONDS)


HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Filmover Device UI</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="topbar">
    <div>
      <h1>Filmover Device UI</h1>
      <p>HX711 로드셀 · 초음파 프리뷰 트리거 · 이벤트 영상 저장</p>
    </div>
    <div class="endpoint">http://{{ host }}:{{ port }}</div>
  </header>

  <main class="layout">
    <section class="panel camera-panel">
      <div class="panel-head">
        <h2>Camera</h2>
        <span id="cameraBadge" class="badge">확인 중</span>
      </div>
      <div class="video-box">
        <img id="video" src="/video_feed" alt="USB camera stream">
        <div id="cameraError" class="overlay"></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>Load Cell</h2>
        <span id="scaleBadge" class="badge">확인 중</span>
      </div>
      <div class="weight">
        <span id="weight">0.0</span>
        <small>g</small>
      </div>
      <button id="tareButton" class="button" type="button">Tare</button>
      <dl class="meta">
        <div><dt>Raw</dt><dd id="rawWeight">0</dd></div>
        <div><dt>Tare</dt><dd id="tareOffset">0</dd></div>
        <div><dt>Updated</dt><dd id="updatedAt">-</dd></div>
        <div><dt>DT / SCK</dt><dd>{{ dout }} / {{ sck }} ({{ pin_mode }})</dd></div>
        <div><dt>Calibration</dt><dd>offset {{ offset }}, scale {{ scale }}</dd></div>
      </dl>
      <p id="scaleError" class="error"></p>
    </section>

    <section class="panel monitor-panel">
      <div class="panel-head">
        <h2>Recording Trigger Mode</h2>
        <span id="monitorBadge" class="badge">IDLE</span>
      </div>
      <div class="sensor-readout">
        <div>
          <span id="distanceValue">0.0</span>
          <small>cm</small>
        </div>
        <span id="ultrasonicBadge" class="badge">확인 중</span>
      </div>
      <form id="monitorForm" class="form-grid">
        <label>
          <span>로드셀 저장 트리거 변화율 g/s</span>
          <input id="weightRate" name="weight_rate_threshold_gps" type="number" step="1" min="0" value="10000">
        </label>
        <label>
          <span>초음파 카메라 ON 기준 cm</span>
          <input id="distanceThreshold" name="ultrasonic_camera_threshold_cm" type="number" step="1" min="1" value="{{ ultrasonic_threshold }}">
        </label>
        <div class="button-row">
          <button id="measureButton" class="button secondary" type="button">Measure</button>
          <button id="armButton" class="button" type="button">Apply Settings</button>
          <button id="resetAlarmButton" class="button danger" type="button">Reset</button>
        </div>
      </form>
      <dl class="meta">
        <div><dt>TRIG/ECHO</dt><dd>{{ ultrasonic_trig }} / {{ ultrasonic_echo }} ({{ ultrasonic_pin_mode }})</dd></div>
        <div><dt>Distance</dt><dd id="distanceUpdatedAt">-</dd></div>
        <div><dt>Camera Trigger</dt><dd id="distanceThresholdStatus">{{ ultrasonic_threshold }}cm 이하</dd></div>
        <div><dt>Buffer</dt><dd id="bufferStatus">-</dd></div>
        <div><dt>Weight Rate</dt><dd id="weightRateStatus">0.0g/s</dd></div>
        <div><dt>Video Dir</dt><dd>{{ video_dir }}</dd></div>
        <div><dt>Last Video</dt><dd id="lastVideoPath">-</dd></div>
        <div><dt>Telegram</dt><dd id="telegramStatus">-</dd></div>
        <div><dt>Baseline</dt><dd id="baselineStatus">-</dd></div>
        <div><dt>Stage</dt><dd id="stageStatus">armed</dd></div>
      </dl>
      <p id="ultrasonicError" class="error"></p>
    </section>
  </main>

  <div id="alarmModal" class="modal" role="alertdialog" aria-modal="true">
    <div class="modal-box">
      <h2>Alarm</h2>
      <p id="alarmMessage">로드셀 변화가 감지되었습니다.</p>
      <button id="alarmCloseButton" class="button danger" type="button">Close</button>
    </div>
  </div>

  <footer>
    Pin source: <code>{{ pin_doc }}</code>
  </footer>

  <script src="/static/app.js"></script>
</body>
</html>
"""


@app.route("/")
def index() -> str:
    return render_template_string(
        HTML,
        host=local_ip(),
        port=os.getenv("FLASK_PORT", "5050"),
        dout=HX711_DOUT_PIN,
        sck=HX711_SCK_PIN,
        pin_mode=HX711_PIN_MODE,
        offset=HX711_OFFSET,
        scale=HX711_SCALE,
        ultrasonic_trig=ULTRASONIC_TRIG_PIN,
        ultrasonic_echo=ULTRASONIC_ECHO_PIN,
        ultrasonic_pin_mode=ULTRASONIC_PIN_MODE,
        ultrasonic_threshold=ULTRASONIC_CAMERA_THRESHOLD_CM,
        video_dir=EVENT_VIDEO_DIR,
        pin_doc=PIN_DOC,
    )


@app.route("/api/status")
def api_status() -> Response:
    return jsonify(asdict(state))


@app.route("/api/tare", methods=["POST"])
def api_tare() -> Response:
    state.tare_offset = state.raw_weight - HX711_OFFSET
    state.weight_g = 0.0
    state.weight_rate_gps = 0.0
    return jsonify(asdict(state))


@app.route("/api/measure", methods=["POST"])
def api_measure() -> Response:
    state.baseline_weight_g = state.weight_g
    return jsonify(asdict(state))


@app.route("/api/monitor", methods=["POST"])
def api_monitor() -> Response:
    payload = flask_request_json()
    if "weight_delta_threshold_g" in payload:
        state.weight_delta_threshold_g = float(payload["weight_delta_threshold_g"])
        state.weight_rate_threshold_gps = state.weight_delta_threshold_g
    state.weight_rate_threshold_gps = float(
        payload.get("weight_rate_threshold_gps", state.weight_rate_threshold_gps)
    )
    state.ultrasonic_camera_threshold_cm = float(
        payload.get("ultrasonic_camera_threshold_cm", state.ultrasonic_camera_threshold_cm)
    )
    state.baseline_weight_g = state.weight_g
    state.monitor_armed = True
    state.monitor_stage = "camera_ready" if state.camera_requested else "armed"
    state.alarm_active = False
    state.alarm_message = ""
    state.alarm_at = ""
    return jsonify(asdict(state))


@app.route("/api/reset", methods=["POST"])
def api_reset() -> Response:
    state.monitor_armed = True
    state.monitor_stage = "camera_ready" if state.camera_requested else "armed"
    state.alarm_active = False
    state.alarm_message = ""
    state.alarm_at = ""
    return jsonify(asdict(state))


def flask_request_json() -> dict:
    from flask import request

    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.route("/video_feed")
def video_feed() -> Response:
    return Response(camera.frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


def start_background_workers() -> None:
    threading.Thread(target=camera.read_loop, args=(state,), daemon=True).start()
    threading.Thread(target=weight_loop, daemon=True).start()
    threading.Thread(target=ultrasonic_loop, daemon=True).start()


if __name__ == "__main__":
    start_background_workers()
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5050")),
        threaded=True,
    )
