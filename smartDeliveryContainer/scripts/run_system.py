#!/usr/bin/env python3
"""SmartDeliveryContainer — 라즈베리파이 로컬 카메라 통합 로직.

동작 흐름:
  1. HC-SR04 ≤ 20cm  →  로컬 카메라 버퍼링 시작 (슬라이딩 30초)
  2. HX711 무게 변화율(g/s) 임계값 초과
       → 텔레그램 알림 메시지 전송
       → 이전 30초 + 이후 10초 영상 MP4 저장
       → MP4 텔레그램 전송
       → 스피커 경보음

실행:
    cd smartDeliveryContainer
    python3 -u scripts/run_system.py
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.alerts.speaker_alarm import SpeakerAlarm
from smart_delivery_container.alerts.telegram_notifier import TelegramNotifier
from smart_delivery_container.camera.camera_recorder import RpiCamBufferedRecorder
from smart_delivery_container.core.config import RuntimeConfig
from smart_delivery_container.sensors.hcsr04_sensor import HcSr04Sensor
from smart_delivery_container.sensors.weight_sensor import HX711WeightSensor
from smart_delivery_container.utils.event_log import log_event


# ── 설정 로드 ──────────────────────────────────────────────────────────────
cfg = RuntimeConfig()

BUFFER_SECONDS      = 30.0   # 이벤트 이전 버퍼 (초)
POST_EVENT_SECONDS  = 10.0   # 이벤트 이후 추가 녹화 (초)
CAMERA_FPS          = 10.0
WEIGHT_COOLDOWN_S   = 12.0   # 연속 이벤트 방지 쿨다운 (초)
# 무게 변화율 임계값 (g/s). 첫 기동 후 웹에서 조정 가능.
# 캘리브레이션 전 raw값 기준이므로 크게 설정.
RATE_THRESHOLD_GPS  = float(__import__('os').getenv("WEIGHT_RATE_THRESHOLD_GPS", "5000"))


def main() -> None:
    # ── 하드웨어 초기화 ────────────────────────────────────────────────────
    cam = RpiCamBufferedRecorder(
        video_dir=cfg.camera.video_output_dir,
        buffer_seconds=BUFFER_SECONDS,
        post_event_seconds=POST_EVENT_SECONDS,
        fps=CAMERA_FPS,
    )

    speaker  = SpeakerAlarm(pin=cfg.speaker.pin, frequency=cfg.speaker.frequency)
    telegram = TelegramNotifier(cfg.telegram.token, cfg.telegram.chat_id)

    def send_warning(title: str, fields: dict[str, str]) -> None:
        speaker.alarm()
        telegram.send(title, fields)

    proximity = HcSr04Sensor(
        trigger_pin=cfg.hcsr04.trigger_pin,
        echo_pin=cfg.hcsr04.echo_pin,
        threshold_cm=cfg.hcsr04.threshold_cm,
    )

    weight_sensor = HX711WeightSensor(
        cfg.weight.hx711_dout_pin, cfg.weight.hx711_sck_pin,
        cfg.weight.calibration_offset, cfg.weight.calibration_scale,
    )

    # ── 상태 변수 ──────────────────────────────────────────────────────────
    prev_weight      = weight_sensor.read_grams()
    prev_weight_at   = time.monotonic()
    last_event_at    = 0.0

    # ── 시작 알림 ──────────────────────────────────────────────────────────
    print("=" * 50)
    print("SmartDeliveryContainer 시작")
    print("  카메라   : Raspberry Pi CSI camera (rpicam)")
    print(f"  초음파   : TRIG=GPIO{cfg.hcsr04.trigger_pin} / ECHO=GPIO{cfg.hcsr04.echo_pin} / {cfg.hcsr04.threshold_cm}cm")
    print(f"  로드셀   : DT=GPIO{cfg.weight.hx711_dout_pin} / SCK=GPIO{cfg.weight.hx711_sck_pin}")
    print(f"  스피커   : GPIO{cfg.speaker.pin}")
    print(f"  텔레그램 : {'활성' if cfg.telegram.token else '비활성'}")
    print(f"  변화율 임계: {RATE_THRESHOLD_GPS}g/s")
    print("=" * 50)

    telegram.send("✅ SmartDeliveryContainer 시작", {
        "초음파 임계값": f"{cfg.hcsr04.threshold_cm}cm",
        "무게 변화율 임계": f"{RATE_THRESHOLD_GPS}g/s",
        "버퍼": f"이전 {BUFFER_SECONDS:.0f}초 + 이후 {POST_EVENT_SECONDS:.0f}초",
    })

    interval = cfg.weight.sample_interval_ms / 1000.0

    try:
        while True:
            now = time.monotonic()

            # ── 1. 초음파 감지 → 카메라 버퍼링 ───────────────────────────
            dist_cm = 999.0
            try:
                dist_cm = proximity.measure_cm()
            except Exception:
                pass

            if dist_cm <= cfg.hcsr04.threshold_cm:
                if not cam.is_buffering:
                    print(f"[초음파] {dist_cm:.1f}cm 감지 → 카메라 버퍼링 시작")
                    cam.start_buffering()
            else:
                if cam.is_buffering:
                    pass  # 버퍼는 계속 유지 (이벤트 후 영상에 필요)

            # ── 2. 로드셀 무게 변화율 감지 ───────────────────────────────
            try:
                weight_g = weight_sensor.read_grams()
            except Exception:
                time.sleep(interval)
                continue

            elapsed = max(now - prev_weight_at, 0.001)
            rate_gps = abs(weight_g - prev_weight) / elapsed
            prev_weight    = weight_g
            prev_weight_at = now

            # 쿨다운 내 중복 이벤트 방지
            if (rate_gps >= RATE_THRESHOLD_GPS
                    and (now - last_event_at) > WEIGHT_COOLDOWN_S):

                last_event_at = now
                event_id = datetime.now().strftime("%Y%m%d%H%M%S")
                ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                print(f"[무게] 변화율 {rate_gps:.0f}g/s 감지 ({weight_g:.0f}g) → 이벤트 발생")
                log_event("weight_event", {
                    "weight_g": weight_g,
                    "rate_gps": round(rate_gps, 1),
                    "dist_cm": round(dist_cm, 1),
                })

                # 텔레그램 경고 메시지와 동시에 스피커 경보
                send_warning("🚨 로드셀 이벤트 감지", {
                    "시각": ts_str,
                    "무게": f"{weight_g:.0f}g",
                    "변화율": f"{rate_gps:.0f}g/s",
                    "거리": f"{dist_cm:.1f}cm",
                    "영상": f"이전 {BUFFER_SECONDS:.0f}초 + 이후 {POST_EVENT_SECONDS:.0f}초 저장 중",
                })

                # 영상 저장 후 텔레그램 전송 (비블로킹)
                if cam.is_buffering:
                    def _on_clip_saved(path: Path) -> None:
                        caption = (
                            f"🎥 이벤트 영상\n"
                            f"시각: {ts_str}\n"
                            f"무게: {weight_g:.0f}g  변화율: {rate_gps:.0f}g/s\n"
                            f"거리: {dist_cm:.1f}cm"
                        )
                        telegram.send_video(path, caption=caption)

                    cam.save_event_clip(event_id, on_done=_on_clip_saved)
                else:
                    print("[무게] 카메라 버퍼 없음 — 초음파 감지 후 이벤트 발생 필요")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n시스템 종료")
    finally:
        cam.stop_buffering()
        proximity.close()
        speaker.close()


if __name__ == "__main__":
    main()
