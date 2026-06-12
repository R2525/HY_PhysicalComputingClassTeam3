#!/usr/bin/env python3
"""카메라 스냅샷 테스트 스크립트.

    python3 scripts/check_camera.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.camera.camera_recorder import OpenCvCameraRecorder
from smart_delivery_container.core.config import CameraConfig
from smart_delivery_container.utils.event_log import log_event


def main() -> None:
    cfg = CameraConfig()
    recorder = OpenCvCameraRecorder(
        cfg.index,
        snapshot_dir=cfg.snapshot_output_dir,
        video_dir=cfg.video_output_dir,
    )
    try:
        snap = recorder.capture_snapshot("test")
        log_event("snapshot_saved", {"path": str(snap)})
        print(f"스냅샷 저장됨: {snap}")
    finally:
        recorder.close()


if __name__ == "__main__":
    main()
