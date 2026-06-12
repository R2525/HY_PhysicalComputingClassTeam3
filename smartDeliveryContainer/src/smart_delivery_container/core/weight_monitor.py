from __future__ import annotations
import time
from typing import Callable

from smart_delivery_container.sensors.weight_sensor import WeightSensor
from smart_delivery_container.sensors.weight_filter import MovingAverageFilter
from smart_delivery_container.core.config import WeightConfig
from smart_delivery_container.core.package_detector import PackageDetector, WeightEvent


class WeightMonitor:
    def __init__(self, sensor: WeightSensor, config: WeightConfig,
                 on_detected: Callable[[WeightEvent], None] | None = None,
                 on_removed: Callable[[WeightEvent], None] | None = None) -> None:
        self._sensor = sensor
        self._cfg = config
        self._filter = MovingAverageFilter(config.moving_average_size)
        self._detector = PackageDetector(config, on_detected=on_detected, on_removed=on_removed)

    def tick(self) -> float:
        raw = self._sensor.read_grams()
        smoothed = self._filter.update(raw)
        self._detector.update(smoothed)
        return smoothed

    def run(self, max_ticks: int | None = None) -> None:
        print("Weight monitor started")
        count = 0
        interval = self._cfg.sample_interval_ms / 1000.0
        while max_ticks is None or count < max_ticks:
            g = self.tick()
            print(f"[WEIGHT] {g:.1f}g  state={self._detector.state.name}")
            time.sleep(interval)
            count += 1
