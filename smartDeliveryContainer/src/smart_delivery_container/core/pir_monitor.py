from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Callable

from smart_delivery_container.sensors.pir_sensor import PirSensor
from smart_delivery_container.core.config import PirConfig
from smart_delivery_container.utils.event_log import log_event


@dataclass
class PirEvent:
    pin: int
    now_ms: int


class PirMonitor:
    def __init__(self, sensor: PirSensor, config: PirConfig,
                 on_motion: Callable[[PirEvent], None] | None = None) -> None:
        self._sensor = sensor
        self._cfg = config
        self._on_motion = on_motion or (lambda e: None)
        self._prev = False
        self._last_event_ms: int = -1

    def tick(self) -> None:
        current = self._sensor.motion_detected()
        now_ms = int(time.monotonic() * 1000)

        rising_edge = current and not self._prev
        cooldown_elapsed = (now_ms - self._last_event_ms) >= self._cfg.cooldown_ms

        if rising_edge and cooldown_elapsed:
            event = PirEvent(pin=self._cfg.pin, now_ms=now_ms)
            log_event("pir_motion_detected", event)
            self._on_motion(event)
            self._last_event_ms = now_ms

        self._prev = current

    def run(self, max_ticks: int | None = None) -> None:
        print(f"PIR monitor started on GPIO {self._cfg.pin}")
        count = 0
        interval = self._cfg.sample_interval_ms / 1000.0
        while max_ticks is None or count < max_ticks:
            self.tick()
            time.sleep(interval)
            count += 1
