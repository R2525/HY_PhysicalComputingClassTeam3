#!/usr/bin/env python3
"""전체 시스템 실행 스크립트.

    python3 scripts/run_system.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.alerts.local_alarm import LocalAlarm
from smart_delivery_container.alerts.mqtt_notifier import MqttNotifier
from smart_delivery_container.camera.camera_recorder import NullCameraRecorder, OpenCvCameraRecorder
from smart_delivery_container.core.config import RuntimeConfig
from smart_delivery_container.core.package_detector import PackageState, WeightEvent
from smart_delivery_container.core.pir_monitor import PirEvent, PirMonitor
from smart_delivery_container.core.weight_monitor import WeightMonitor
from smart_delivery_container.sensors.pir_sensor import GpioPirSensor
from smart_delivery_container.sensors.weight_sensor import HX711WeightSensor
from smart_delivery_container.utils.event_log import log_event


def main() -> None:
    cfg = RuntimeConfig()

    alarm = LocalAlarm()
    notifier = MqttNotifier(cfg.mqtt.host, cfg.mqtt.port, cfg.mqtt.topic)

    try:
        recorder = OpenCvCameraRecorder(
            cfg.camera.index,
            snapshot_dir=cfg.camera.snapshot_output_dir,
            video_dir=cfg.camera.video_output_dir,
        )
    except Exception:
        recorder = NullCameraRecorder(
            snapshot_dir=cfg.camera.snapshot_output_dir,
            video_dir=cfg.camera.video_output_dir,
        )

    pir_sensor = GpioPirSensor(cfg.pir.pin)
    weight_sensor = HX711WeightSensor(
        cfg.weight.hx711_dout_pin, cfg.weight.hx711_sck_pin,
        cfg.weight.calibration_offset, cfg.weight.calibration_scale,
    )

    # --- 공유 상태 ---
    _pir_active = False

    def on_pir(event: PirEvent) -> None:
        nonlocal _pir_active
        _pir_active = True
        snap = recorder.capture_snapshot(f"pir{event.now_ms}")
        log_event("snapshot_saved", {"path": str(snap)})

    def on_package_detected(event: WeightEvent) -> None:
        log_event("guard_mode_entered", {"weight_g": event.weight_g})

    def on_package_removed(event: WeightEvent) -> None:
        nonlocal _pir_active
        if _pir_active:
            clip = recorder.record_clip(f"theft{int(time.monotonic()*1000)}", 10)
            log_event("theft_confirmed", {"weight_g": event.weight_g, "clip": str(clip)})
            alarm.play()
            notifier.send("theft_confirmed", {"weight_g": event.weight_g})
        else:
            log_event("suspicious_weight_change", {"weight_g": event.weight_g})
        _pir_active = False

    pir_monitor = PirMonitor(pir_sensor, cfg.pir, on_motion=on_pir)
    weight_monitor = WeightMonitor(
        weight_sensor, cfg.weight,
        on_detected=on_package_detected,
        on_removed=on_package_removed,
    )

    print("SmartDeliveryContainer 시스템 시작")
    interval_pir = cfg.pir.sample_interval_ms / 1000.0
    interval_weight = cfg.weight.sample_interval_ms / 1000.0

    try:
        while True:
            pir_monitor.tick()
            weight_monitor.tick()
            time.sleep(min(interval_pir, interval_weight))
    except KeyboardInterrupt:
        print("\n시스템 종료")
    finally:
        pir_sensor.close()
        alarm.close()
        notifier.close()


if __name__ == "__main__":
    main()
