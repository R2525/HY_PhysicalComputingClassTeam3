from __future__ import annotations
import time

from smart_delivery_container.sensors.pir_sensor import PirSensor
from smart_delivery_container.camera.camera_recorder import CameraRecorder
from smart_delivery_container.core.config import PirConfig
from smart_delivery_container.core.pir_monitor import PirEvent, PirMonitor
from smart_delivery_container.utils.event_log import log_event


class PirCameraMonitor:
    def __init__(self, sensor: PirSensor, recorder: CameraRecorder,
                 config: PirConfig, record_seconds: int = 0) -> None:
        self._recorder = recorder
        self._record_seconds = record_seconds
        self._monitor = PirMonitor(sensor, config, on_motion=self._handle_motion)

    def _handle_motion(self, event: PirEvent) -> None:
        event_id = f"pir{event.now_ms}"
        snap = self._recorder.capture_snapshot(event_id)
        log_event("snapshot_saved", {"path": str(snap), "pir_now_ms": event.now_ms})
        if self._record_seconds > 0:
            clip = self._recorder.record_clip(event_id, self._record_seconds)
            log_event("clip_saved", {"path": str(clip), "pir_now_ms": event.now_ms})

    def run(self, max_ticks: int | None = None) -> None:
        self._monitor.run(max_ticks=max_ticks)
