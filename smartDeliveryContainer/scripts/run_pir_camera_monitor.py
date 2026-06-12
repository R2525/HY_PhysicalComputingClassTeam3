#!/usr/bin/env python3
"""PIR + 카메라 연동 테스트 스크립트.

    python3 scripts/run_pir_camera_monitor.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.camera.camera_recorder import OpenCvCameraRecorder
from smart_delivery_container.core.config import CameraConfig, PirConfig
from smart_delivery_container.core.pir_camera_monitor import PirCameraMonitor
from smart_delivery_container.sensors.pir_sensor import GpioPirSensor


def main() -> None:
    pir_cfg = PirConfig()
    cam_cfg = CameraConfig()

    sensor = GpioPirSensor(pir_cfg.pin)
    recorder = OpenCvCameraRecorder(
        cam_cfg.index,
        snapshot_dir=cam_cfg.snapshot_output_dir,
        video_dir=cam_cfg.video_output_dir,
    )
    monitor = PirCameraMonitor(sensor, recorder, pir_cfg, record_seconds=5)
    try:
        monitor.run()
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()
        recorder.close()


if __name__ == "__main__":
    main()
