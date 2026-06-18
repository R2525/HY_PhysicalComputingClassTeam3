#!/usr/bin/env python3
"""
Raspberry Pi Camera + HX711 로드셀 통합 서버.
- 무게 실시간 모니터링 (SSE)
- 초음파 감지 시 카메라 버퍼링 시작
- 무게 알람 발생 시 이전 최대 30초 + 이후 10초를 하나의 MP4로 전송
- Flask 웹 UI: 카메라 스트림 + 무게 게이지 + 캡처 이력
"""

import io
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
import tempfile
from collections import deque
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, send_from_directory


APP_DIR = Path(__file__).parent
PROJECT_DIR = APP_DIR.parents[1] / "smartDeliveryContainer"
load_dotenv(PROJECT_DIR / "config" / ".env", override=False)

# ── 설정 ──────────────────────────────────────────────────────────────────
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
CAMERA_FPS = int(float(os.getenv("CAMERA_FPS", "10")))

# HX711 GPIO 핀 (BCM 번호)
HX711_DATA_PIN = 5   # 물리 핀 29
HX711_CLK_PIN  = 6   # 물리 핀 31

# HC-SR04 GPIO 핀 (BCM 번호)
HCSR04_TRIGGER_PIN = 23  # 물리 핀 16
HCSR04_ECHO_PIN    = 24  # 물리 핀 18
HCSR04_THRESHOLD_CM = float(os.getenv("HCSR04_THRESHOLD_CM", "200.0"))

# 스피커 GPIO 핀 (BCM 번호)
SPEAKER_PIN       = int(os.getenv("SPEAKER_PIN", "18"))      # 물리 핀 12
SPEAKER_FREQUENCY = int(os.getenv("SPEAKER_FREQUENCY", "2000"))
SPEAKER_DUTY      = float(os.getenv("SPEAKER_DUTY_CYCLE", "20"))

# 무게 설정 (calibration 후 조정)
WEIGHT_THRESHOLD = 500   # g — 이 값 초과 시 이벤트 영상 전송
TARE_OFFSET      = 0     # 영점 오프셋 (calibrate() 로 갱신됨)
SCALE_FACTOR     = 1.0   # 스케일 인수 (calibrate() 로 갱신됨)
WEIGHT_AVG_WINDOW_S = 5.0
WEIGHT_SPIKE_DELTA_G = 250.0
WEIGHT_CANDIDATE_WINDOW_S = 5.0
WEIGHT_CANDIDATE_MAX_SPREAD_G = 120.0
PRE_EVENT_BUFFER_SECONDS = float(os.getenv("PRE_EVENT_BUFFER_SECONDS", "30"))
POST_EVENT_SECONDS = float(os.getenv("POST_EVENT_SECONDS", "10"))
TELEGRAM_VIDEO_FPS = float(os.getenv("TELEGRAM_VIDEO_FPS", "10"))
EVENT_COOLDOWN_SECONDS = float(os.getenv("EVENT_COOLDOWN_SECONDS", "10"))
AUTO_TARE_ENABLED = True
AUTO_TARE_STABLE_S = 20.0
AUTO_TARE_MAX_ABS_G = 80.0
AUTO_TARE_MAX_SPREAD_G = 35.0
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)
VIDEO_DIR = Path(__file__).parent / "videos"
VIDEO_DIR.mkdir(exist_ok=True)


def get_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"

# ── 전역 상태 ──────────────────────────────────────────────────────────────
state = {
    "weight": 0.0,
    "raw_weight": 0.0,
    "avg_weight": 0.0,
    "raw": 0,
    "pending_weight": None,
    "pending_seconds": 0.0,
    "pending_stable": False,
    "threshold": WEIGHT_THRESHOLD,
    "triggered": False,
    "last_trigger_time": None,
    "snapshots": [],          # 수동 스냅샷 이력
    "videos": [],             # {"time": str, "filename": str, "weight": float}
    "camera_ready": False,
    "camera_error": None,
    "camera_requested": False,
    "camera_buffer_started_at": None,
    "camera_buffer_seconds": 0.0,
    "camera_buffer_frames": 0,
    "video_saving": False,
    "distance_cm": None,
    "proximity": False,
    "ultrasonic_ready": False,
    "ultrasonic_logs": [],
    "auto_tare_enabled": AUTO_TARE_ENABLED,
    "last_auto_tare_time": None,
    "telegram_enabled": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
    "last_telegram_time": None,
    "hx_ready": False,
    "error": None,
}
state_lock = threading.Lock()

# ── 스피커 초기화 ──────────────────────────────────────────────────────────
_speaker_pwm = None
_speaker_gpio = None

def _init_speaker() -> None:
    global _speaker_pwm, _speaker_gpio
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SPEAKER_PIN, GPIO.OUT)
        _speaker_pwm = GPIO.PWM(SPEAKER_PIN, SPEAKER_FREQUENCY)
        _speaker_gpio = GPIO
        print(f"[SPEAKER] 초기화 완료 — GPIO{SPEAKER_PIN}, {SPEAKER_FREQUENCY}Hz")
    except Exception as e:
        print(f"[SPEAKER] 초기화 실패 (콘솔 모드): {e}")

def _beep(duration: float, freq: int) -> None:
    if _speaker_pwm is None:
        return
    _speaker_pwm.ChangeFrequency(freq)
    _speaker_pwm.start(SPEAKER_DUTY)
    time.sleep(duration)
    _speaker_pwm.stop()

def alarm_speaker() -> None:
    def _play():
        for _ in range(3):
            _beep(0.12, 1800)
            time.sleep(0.12)
            _beep(0.12, 1000)
            time.sleep(0.08)
    threading.Thread(target=_play, daemon=True).start()

# ── HX711 초기화 ───────────────────────────────────────────────────────────
hx = None
ultra_gpio = None
camera_condition = threading.Condition()
camera_frames = deque()
latest_jpeg = None
latest_jpeg_ts = 0.0
camera_started_monotonic: float | None = None
camera_requested = threading.Event()
event_send_lock = threading.Lock()


def _add_ultrasonic_log(distance_cm: float, detected: bool, note: str = "") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "distance": round(distance_cm, 1),
        "detected": detected,
        "note": note,
    }
    with state_lock:
        state["ultrasonic_logs"].insert(0, entry)
        state["ultrasonic_logs"] = state["ultrasonic_logs"][:30]


def send_telegram_message(text: str) -> None:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[TELEGRAM] 토큰/채팅ID 미설정")
        return
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
        with state_lock:
            state["last_telegram_time"] = datetime.now().strftime("%H:%M:%S")
    except Exception as e:
        print(f"[TELEGRAM] 메시지 전송 실패: {e}")
        with state_lock:
            state["error"] = f"Telegram: {e}"


def send_telegram_photo(path: Path, caption: str) -> None:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID) or not path.exists():
        return
    boundary = "SdcBoundary"
    buf = bytearray()

    def part(name: str, value: bytes, filename: str = "") -> None:
        buf.extend(f"--{boundary}\r\n".encode())
        disp = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disp += f'; filename="{filename}"'
        buf.extend(f"{disp}\r\n".encode())
        if filename:
            buf.extend(b"Content-Type: image/jpeg\r\n")
        buf.extend(b"\r\n")
        buf.extend(value)
        buf.extend(b"\r\n")

    part("chat_id", TELEGRAM_CHAT_ID.encode())
    part("caption", caption.encode())
    part("photo", path.read_bytes(), filename=path.name)
    buf.extend(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
        data=bytes(buf),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20):
            pass
        with state_lock:
            state["last_telegram_time"] = datetime.now().strftime("%H:%M:%S")
    except Exception as e:
        print(f"[TELEGRAM] 사진 전송 실패: {e}")
        with state_lock:
            state["error"] = f"Telegram: {e}"


def store_camera_frame(jpeg: bytes) -> None:
    global latest_jpeg, latest_jpeg_ts
    now = time.monotonic()
    with camera_condition:
        latest_jpeg = jpeg
        latest_jpeg_ts = now
        camera_frames.append((now, jpeg))
        cutoff = now - PRE_EVENT_BUFFER_SECONDS
        while camera_frames and camera_frames[0][0] < cutoff:
            camera_frames.popleft()
        with state_lock:
            state["camera_buffer_frames"] = len(camera_frames)
            state["camera_buffer_seconds"] = round(
                camera_frames[-1][0] - camera_frames[0][0], 1
            ) if len(camera_frames) >= 2 else 0.0
        camera_condition.notify_all()


def start_camera_buffering(reason: str) -> None:
    global camera_started_monotonic
    if camera_requested.is_set():
        return
    with camera_condition:
        camera_frames.clear()
        camera_condition.notify_all()
    camera_started_monotonic = time.monotonic()
    with state_lock:
        state["camera_requested"] = True
        state["camera_buffer_started_at"] = datetime.now().strftime("%H:%M:%S")
        state["camera_buffer_seconds"] = 0.0
        state["camera_buffer_frames"] = 0
    camera_requested.set()
    print(f"[CAM] 버퍼링 요청: {reason}")


def camera_reader_loop() -> None:
    """rpicam-vid MJPEG 출력을 읽고 내부 버퍼에 저장한다."""
    cmd = [
        "rpicam-vid",
        "--timeout", "0",
        "--codec", "mjpeg",
        "--width", str(CAMERA_WIDTH),
        "--height", str(CAMERA_HEIGHT),
        "--framerate", str(CAMERA_FPS),
        "--nopreview",
        "--output", "-",
    ]
    while True:
        camera_requested.wait()
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if proc.stdout is None:
                raise RuntimeError("rpicam-vid stdout 연결 실패")

            raw = b""
            with state_lock:
                state["camera_ready"] = True
                state["camera_error"] = None
            print("[CAM] rpicam 스트림 시작")

            while camera_requested.is_set():
                chunk = proc.stdout.read(4096)
                if not chunk:
                    raise RuntimeError("rpicam-vid output ended")
                raw += chunk
                while True:
                    start = raw.find(b"\xff\xd8")
                    if start == -1:
                        raw = raw[-1:]
                        break
                    end = raw.find(b"\xff\xd9", start)
                    if end == -1:
                        raw = raw[start:]
                        break
                    jpeg = raw[start:end + 2]
                    raw = raw[end + 2:]
                    store_camera_frame(jpeg)
        except Exception as e:
            print(f"[CAM] rpicam reader failed: {e}")
            with state_lock:
                state["camera_ready"] = False
                state["camera_error"] = str(e)
            time.sleep(2)
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
            with state_lock:
                state["camera_ready"] = False


def get_latest_jpeg(timeout: float = 2.0) -> bytes | None:
    deadline = time.monotonic() + timeout
    with camera_condition:
        while latest_jpeg is None and time.monotonic() < deadline:
            camera_condition.wait(timeout=0.2)
        return latest_jpeg


def send_telegram_video(path: Path, caption: str) -> None:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID) or not path.exists():
        return
    boundary = "SdcBoundary"
    buf = bytearray()

    def part(name: str, value: bytes, filename: str = "") -> None:
        buf.extend(f"--{boundary}\r\n".encode())
        disp = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disp += f'; filename="{filename}"'
        buf.extend(f"{disp}\r\n".encode())
        if filename:
            buf.extend(b"Content-Type: video/mp4\r\n")
        buf.extend(b"\r\n")
        buf.extend(value)
        buf.extend(b"\r\n")

    part("chat_id", TELEGRAM_CHAT_ID.encode())
    part("caption", caption.encode())
    part("video", path.read_bytes(), filename=path.name)
    buf.extend(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo",
        data=bytes(buf),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180):
            pass
        with state_lock:
            state["last_telegram_time"] = datetime.now().strftime("%H:%M:%S")
    except Exception as e:
        print(f"[TELEGRAM] 영상 전송 실패: {e}")
        with state_lock:
            state["error"] = f"Telegram: {e}"


def record_event_video(event_id: str,
                       event_time: float,
                       post_seconds: float = POST_EVENT_SECONDS) -> Path:
    """이벤트 이전 버퍼와 이벤트 이후 프레임을 하나의 MP4로 저장한다."""
    path = VIDEO_DIR / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{event_id}.mp4"
    camera_start = camera_started_monotonic or event_time
    cutoff = max(camera_start, event_time - PRE_EVENT_BUFFER_SECONDS)

    with camera_condition:
        frames = [(ts, jpeg) for ts, jpeg in camera_frames if ts >= cutoff]
        pre_seconds = max(0.0, event_time - frames[0][0]) if frames else 0.0

    deadline = event_time + post_seconds
    last_ts = frames[-1][0] if frames else 0.0
    while time.monotonic() < deadline:
        with camera_condition:
            camera_condition.wait(timeout=0.5)
            new_frames = [
                (ts, jpeg) for ts, jpeg in camera_frames
                if ts > last_ts and ts <= deadline
            ]
        if new_frames:
            frames.extend(new_frames)
            last_ts = frames[-1][0]

    if not frames:
        raise RuntimeError("영상 프레임을 저장하지 못했습니다")

    frame_count = 0
    with tempfile.TemporaryDirectory(prefix="sdc_frames_") as tmpdir:
        tmp_path = Path(tmpdir)
        for _, jpeg in frames:
            frame_count += 1
            (tmp_path / f"frame_{frame_count:06d}.jpg").write_bytes(jpeg)

        if frame_count == 0:
            raise RuntimeError("영상 프레임을 저장하지 못했습니다")

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-framerate", str(TELEGRAM_VIDEO_FPS),
            "-i", str(tmp_path / "frame_%06d.jpg"),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(path),
        ]
        subprocess.run(cmd, check=True)

    actual_seconds = frame_count / TELEGRAM_VIDEO_FPS if TELEGRAM_VIDEO_FPS else 0.0
    print(
        f"[CAM] 영상 저장 완료: {path.name} "
        f"({frame_count} frames, {actual_seconds:.1f}s, "
        f"pre={pre_seconds:.1f}s, post={post_seconds:.1f}s, h264)"
    )
    return path


def record_and_send_telegram_video(event_id: str, caption: str, event_time: float, weight_g: float) -> None:
    try:
        with state_lock:
            state["video_saving"] = True
        video = record_event_video(event_id, event_time)
        ts = datetime.now().strftime("%H:%M:%S")
        with state_lock:
            state["videos"].insert(0, {
                "time": ts,
                "filename": video.name,
                "weight": round(weight_g, 1),
            })
            state["videos"] = state["videos"][:20]
        send_telegram_video(video, caption)
    except Exception as e:
        print(f"[CAM] 영상 저장/전송 실패: {e}")
        send_telegram_message(caption + f"\n영상 저장 실패: {e}")
    finally:
        with state_lock:
            state["video_saving"] = False
        event_send_lock.release()


def _read_raw_timeout(hx_obj, times=5, timeout=5.0):
    """get_raw_data()를 타임아웃 내에 실행, 실패 시 None 반환."""
    result = [None]
    done = threading.Event()
    def _do():
        data = hx_obj.get_raw_data(times=times)
        result[0] = data
        done.set()
    threading.Thread(target=_do, daemon=True).start()
    if done.wait(timeout) and result[0]:
        return result[0]
    return None


def init_hx711():
    """HX711 전체 초기화를 타임아웃 스레드로 실행 (reset() 자체도 블로킹)."""
    global hx, TARE_OFFSET
    result = {"hx": None, "offset": 0.0, "ok": False, "err": None}
    done = threading.Event()

    def _init():
        try:
            from hx711 import HX711
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            obj = HX711(dout_pin=HX711_DATA_PIN, pd_sck_pin=HX711_CLK_PIN)
            obj.reset()                          # 내부적으로 get_raw_data() 호출
            data = obj.get_raw_data(times=10)
            if data:
                result["offset"] = sum(data) / len(data)
                result["hx"] = obj
                result["ok"] = True
        except Exception as e:
            result["err"] = str(e)
        finally:
            done.set()

    threading.Thread(target=_init, daemon=True).start()

    if done.wait(timeout=10.0) and result["ok"]:
        hx = result["hx"]
        TARE_OFFSET = result["offset"]
        with state_lock:
            state["hx_ready"] = True
        print(f"[HX711] 초기화 완료 — offset={TARE_OFFSET:.0f}")
    else:
        msg = result["err"] or "응답 없음 — 배선 확인 필요 (GPIO5=DT, GPIO6=CLK)"
        with state_lock:
            state["error"] = f"HX711: {msg}"
        print(f"[HX711] {msg}")


def read_weight_loop():
    """백그라운드에서 100ms 마다 무게 읽기.

    판정은 5초 이동 평균을 사용한다. accepted_weight에서 크게 튄 값은
    바로 반영하지 않고 후보 버퍼에 보관한다. 후보 값들이 5초 동안
    비슷하게 유지될 때만 실제로 물건이 올라간 변화로 승격한다.
    """
    global TARE_OFFSET
    cooldown = EVENT_COOLDOWN_SECONDS
    last_trigger = 0.0
    samples = deque()
    raw_samples = deque()
    stable_samples = deque()
    pending_samples = deque()
    accepted_weight = 0.0
    last_auto_tare = 0.0
    was_over_threshold = False

    while True:
        try:
            if hx is None or not state["hx_ready"]:
                time.sleep(0.5)
                continue

            data = _read_raw_timeout(hx, times=3, timeout=2.0)
            if not data:
                time.sleep(0.2)
                continue
            raw_val = sum(data) / len(data)
            raw_weight_g = (raw_val - TARE_OFFSET) / SCALE_FACTOR if SCALE_FACTOR != 0 else 0.0

            now = time.time()
            pending_weight = None
            pending_seconds = 0.0
            pending_stable = False

            if abs(raw_weight_g - accepted_weight) >= WEIGHT_SPIKE_DELTA_G:
                pending_samples.append((now, raw_weight_g))
                pending_cutoff = now - WEIGHT_CANDIDATE_WINDOW_S
                while pending_samples and pending_samples[0][0] < pending_cutoff:
                    pending_samples.popleft()

                pending_values = [v for _, v in pending_samples]
                pending_weight = sum(pending_values) / len(pending_values)
                pending_seconds = pending_samples[-1][0] - pending_samples[0][0] if len(pending_samples) > 1 else 0.0
                pending_spread = max(pending_values) - min(pending_values)
                pending_stable = (
                    pending_seconds >= WEIGHT_CANDIDATE_WINDOW_S - 0.3
                    and pending_spread <= WEIGHT_CANDIDATE_MAX_SPREAD_G
                )
                if pending_stable:
                    accepted_weight = pending_weight
                    pending_samples.clear()
                    samples.clear()
                    samples.append((now, accepted_weight))
            else:
                accepted_weight = raw_weight_g
                pending_samples.clear()

            samples.append((now, accepted_weight))
            raw_samples.append((now, raw_val))
            cutoff = now - WEIGHT_AVG_WINDOW_S
            while samples and samples[0][0] < cutoff:
                samples.popleft()
            while raw_samples and raw_samples[0][0] < cutoff:
                raw_samples.popleft()

            avg_weight = sum(v for _, v in samples) / len(samples)
            over_threshold = abs(avg_weight) >= state["threshold"]
            triggered = (
                not over_threshold
                and was_over_threshold
                and (now - last_trigger) > cooldown
                and not state["video_saving"]
            )
            was_over_threshold = over_threshold

            stable_samples.append((now, avg_weight))
            stable_cutoff = now - AUTO_TARE_STABLE_S
            while stable_samples and stable_samples[0][0] < stable_cutoff:
                stable_samples.popleft()

            auto_tare_done = False
            if AUTO_TARE_ENABLED and raw_samples and stable_samples:
                stable_values = [v for _, v in stable_samples]
                stable_age = stable_samples[-1][0] - stable_samples[0][0]
                spread = max(stable_values) - min(stable_values)
                near_zero = abs(avg_weight) <= AUTO_TARE_MAX_ABS_G
                stable = stable_age >= AUTO_TARE_STABLE_S - 0.5 and spread <= AUTO_TARE_MAX_SPREAD_G
                if near_zero and stable and (now - last_auto_tare) >= AUTO_TARE_STABLE_S:
                    TARE_OFFSET = sum(v for _, v in raw_samples) / len(raw_samples)
                    accepted_weight = 0.0
                    samples.clear()
                    samples.append((now, 0.0))
                    stable_samples.clear()
                    stable_samples.append((now, 0.0))
                    avg_weight = 0.0
                    last_auto_tare = now
                    auto_tare_done = True

            with state_lock:
                state["raw_weight"] = round(raw_weight_g, 1)
                state["weight"] = round(accepted_weight, 1)
                state["avg_weight"] = round(avg_weight, 1)
                state["raw"] = raw_val
                state["pending_weight"] = round(pending_weight, 1) if pending_weight is not None else None
                state["pending_seconds"] = round(pending_seconds, 1)
                state["pending_stable"] = pending_stable
                state["triggered"] = triggered
                if auto_tare_done:
                    state["last_auto_tare_time"] = datetime.now().strftime("%H:%M:%S")

            if triggered:
                if not event_send_lock.acquire(blocking=False):
                    time.sleep(0.1)
                    continue

                last_trigger = now
                event_time = time.monotonic()
                if not camera_requested.is_set():
                    start_camera_buffering("무게 알람")
                ts = datetime.now().strftime("%H:%M:%S")
                with state_lock:
                    state["last_trigger_time"] = ts
                    state["video_saving"] = True
                alarm_speaker()
                print(f"[트리거] avg={avg_weight:.1f}g raw={raw_weight_g:.1f}g → 영상 저장 예약")
                distance = state.get("distance_cm")
                with state_lock:
                    buffered_seconds = state["camera_buffer_seconds"]
                caption = (
                    f"SmartDeliveryContainer 알림\n"
                    f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"5초 평균: {avg_weight:.1f}g\n"
                    f"원본: {raw_weight_g:.1f}g\n"
                    f"초음파: {distance if distance is not None else '--'}cm\n"
                    f"영상: 이전 저장분 {min(buffered_seconds, PRE_EVENT_BUFFER_SECONDS):.1f}초 + 이후 {POST_EVENT_SECONDS:.0f}초"
                )
                event_id = datetime.now().strftime("%Y%m%d%H%M%S")
                threading.Thread(
                    target=record_and_send_telegram_video,
                    args=(event_id, caption, event_time, avg_weight),
                    daemon=True,
                ).start()

        except Exception as e:
            with state_lock:
                state["error"] = str(e)

        time.sleep(0.1)


def init_ultrasonic():
    """HC-SR04 초기화."""
    global ultra_gpio
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(HCSR04_TRIGGER_PIN, GPIO.OUT)
        GPIO.setup(HCSR04_ECHO_PIN, GPIO.IN)
        GPIO.output(HCSR04_TRIGGER_PIN, False)
        ultra_gpio = GPIO
        with state_lock:
            state["ultrasonic_ready"] = True
        print(f"[HC-SR04] 초기화 완료 — TRIG=GPIO{HCSR04_TRIGGER_PIN}, ECHO=GPIO{HCSR04_ECHO_PIN}")
        time.sleep(0.05)
    except Exception as e:
        with state_lock:
            state["error"] = f"HC-SR04: {e}"
        print(f"[HC-SR04] 초기화 실패: {e}")


def measure_distance_cm() -> float:
    """HC-SR04 거리 측정. 타임아웃은 999.0cm로 반환."""
    GPIO = ultra_gpio
    if GPIO is None:
        return 999.0

    GPIO.output(HCSR04_TRIGGER_PIN, True)
    time.sleep(0.00001)
    GPIO.output(HCSR04_TRIGGER_PIN, False)

    deadline = time.monotonic() + 0.04
    while GPIO.input(HCSR04_ECHO_PIN) == 0:
        if time.monotonic() > deadline:
            return 999.0
    pulse_start = time.monotonic()

    deadline = time.monotonic() + 0.04
    while GPIO.input(HCSR04_ECHO_PIN) == 1:
        if time.monotonic() > deadline:
            return 999.0
    pulse_end = time.monotonic()

    duration_us = (pulse_end - pulse_start) * 1_000_000
    return duration_us / 2.0 * 0.0343


def read_ultrasonic_loop():
    """초음파 거리 측정과 UI 로그 업데이트."""
    last_state = None
    last_log = 0.0
    while True:
        try:
            if ultra_gpio is None:
                time.sleep(0.5)
                continue

            distance = measure_distance_cm()
            detected = distance <= HCSR04_THRESHOLD_CM
            now = time.time()
            note = ""
            should_log = False
            if last_state is None or detected != last_state:
                note = "접근 감지" if detected else "감지 해제"
                should_log = True
                if detected:
                    start_camera_buffering("초음파 감지")
            elif now - last_log >= 5.0:
                should_log = True

            with state_lock:
                state["distance_cm"] = round(distance, 1)
                state["proximity"] = detected

            if should_log:
                _add_ultrasonic_log(distance, detected, note)
                last_log = now
                last_state = detected
        except Exception as e:
            with state_lock:
                state["error"] = f"HC-SR04: {e}"
        time.sleep(0.2)


# ── 스냅샷 캡처 ────────────────────────────────────────────────────────────
def capture_snapshot(weight: float) -> str:
    """내부 카메라 버퍼의 최신 JPEG 프레임을 파일로 저장."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"snap_{ts}_{int(weight)}g.jpg"
    filepath = SNAPSHOT_DIR / filename
    try:
        jpeg = get_latest_jpeg(timeout=3.0)
        if jpeg is None:
            raise RuntimeError("카메라 프레임 없음")
        filepath.write_bytes(jpeg)
        return filename
    except Exception as e:
        print(f"[스냅샷 오류] {e}")
        return ""


# ── Flask 앱 ───────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=str(APP_DIR / "templates"))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stream")
def stream():
    def proxy():
        boundary = b"--123456789000000000000987654321\r\n"
        last_ts = 0.0
        while True:
            with camera_condition:
                camera_condition.wait(timeout=2.0)
                frame = camera_frames[-1] if camera_frames else None
            if frame is None:
                continue
            ts, jpeg = frame
            if ts <= last_ts:
                continue
            last_ts = ts
            yield boundary
            yield f"Content-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
            yield jpeg
            yield b"\r\n"
    return Response(
        proxy(),
        content_type="multipart/x-mixed-replace;boundary=123456789000000000000987654321",
    )


@app.route("/weight-stream")
def weight_stream():
    """SSE — 브라우저에 무게 데이터 실시간 푸시."""
    def generate():
        while True:
            with state_lock:
                payload = {
                    "weight":  state["weight"],
                    "raw_weight": state["raw_weight"],
                    "avg_weight": state["avg_weight"],
                    "pending_weight": state["pending_weight"],
                    "pending_seconds": state["pending_seconds"],
                    "pending_stable": state["pending_stable"],
                    "threshold": state["threshold"],
                    "triggered": state["triggered"],
                    "hx_ready":  state["hx_ready"],
                    "distance_cm": state["distance_cm"],
                    "proximity": state["proximity"],
                    "ultrasonic_ready": state["ultrasonic_ready"],
                    "ultrasonic_logs": state["ultrasonic_logs"][:10],
                    "camera_ready": state["camera_ready"],
                    "camera_requested": state["camera_requested"],
                    "camera_buffer_seconds": state["camera_buffer_seconds"],
                    "camera_buffer_frames": state["camera_buffer_frames"],
                    "video_saving": state["video_saving"],
                    "auto_tare_enabled": state["auto_tare_enabled"],
                    "last_auto_tare_time": state["last_auto_tare_time"],
                    "telegram_enabled": state["telegram_enabled"],
                    "last_telegram_time": state["last_telegram_time"],
                    "error":     state["error"],
                    "snapshots": state["snapshots"][:5],
                    "videos": state["videos"][:5],
                }
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(0.2)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/tare", methods=["POST"])
def tare():
    global TARE_OFFSET
    if hx:
        data = _read_raw_timeout(hx, times=10, timeout=6.0)
        if data:
            TARE_OFFSET = sum(data) / len(data)
            with state_lock:
                state["last_auto_tare_time"] = datetime.now().strftime("%H:%M:%S")
            return jsonify({"ok": True, "offset": TARE_OFFSET})
        return jsonify({"ok": False, "error": "HX711 응답 없음"})
    return jsonify({"ok": False, "error": "HX711 없음"})


@app.route("/threshold/<int:value>", methods=["POST"])
def set_threshold(value):
    with state_lock:
        state["threshold"] = value
    return jsonify({"ok": True, "threshold": value})


@app.route("/snapshot-now", methods=["POST"])
def snapshot_now():
    with state_lock:
        w = state["weight"]
    fname = capture_snapshot(w)
    if fname:
        ts = datetime.now().strftime("%H:%M:%S")
        with state_lock:
            state["snapshots"].insert(0, {"time": ts, "filename": fname, "weight": w})
        return jsonify({"ok": True, "filename": fname})
    return jsonify({"ok": False})


@app.route("/snapshots/<path:filename>")
def snapshot_file(filename):
    return send_from_directory(SNAPSHOT_DIR, filename)


@app.route("/status")
def status():
    with state_lock:
        snap_count = len(state["snapshots"])
        hx_ready = state["hx_ready"]
        ultrasonic_ready = state["ultrasonic_ready"]
        telegram_enabled = state["telegram_enabled"]
        camera_requested_state = state["camera_requested"]
        camera_buffer_seconds = state["camera_buffer_seconds"]
        camera_buffer_frames = state["camera_buffer_frames"]
        video_saving = state["video_saving"]
    online = time.monotonic() - latest_jpeg_ts < 5.0
    return jsonify({"cam_online": online, "hx_ready": hx_ready,
                    "ultrasonic_ready": ultrasonic_ready,
                    "telegram_enabled": telegram_enabled,
                    "snapshots": snap_count,
                    "camera_requested": camera_requested_state,
                    "camera_buffer_seconds": camera_buffer_seconds,
                    "camera_buffer_frames": camera_buffer_frames,
                    "video_saving": video_saving})


if __name__ == "__main__":
    _init_speaker()
    # HX711 초기화 & 무게 읽기 스레드 시작
    threading.Thread(target=init_hx711, daemon=True).start()
    threading.Thread(target=read_weight_loop, daemon=True).start()
    threading.Thread(target=init_ultrasonic, daemon=True).start()
    threading.Thread(target=read_ultrasonic_loop, daemon=True).start()
    threading.Thread(target=camera_reader_loop, daemon=True).start()

    host_ip = get_ip()
    print(f"서버: http://{host_ip}:5000")
    print(f"카메라: Raspberry Pi CSI camera via rpicam-vid ({CAMERA_WIDTH}x{CAMERA_HEIGHT}@{CAMERA_FPS}fps)")
    print(f"HX711: DATA=GPIO{HX711_DATA_PIN}, CLK=GPIO{HX711_CLK_PIN}")
    print(f"HC-SR04: TRIG=GPIO{HCSR04_TRIGGER_PIN}, ECHO=GPIO{HCSR04_ECHO_PIN}, {HCSR04_THRESHOLD_CM}cm")
    print(f"스피커: GPIO{SPEAKER_PIN}, {SPEAKER_FREQUENCY}Hz")
    print(f"Telegram: {'enabled' if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID else 'disabled'}")
    print(f"트리거 임계값: {WEIGHT_THRESHOLD}g, {WEIGHT_AVG_WINDOW_S:.0f}초 평균 기준")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
