from __future__ import annotations
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from smart_delivery_container.core.config import WeightConfig
from smart_delivery_container.utils.event_log import log_event


class PackageState(Enum):
    IDLE = auto()
    GUARD_MODE = auto()


@dataclass
class WeightEvent:
    weight_g: float
    reference_g: float | None = None


class PackageDetector:
    def __init__(self, config: WeightConfig,
                 on_detected: Callable[[WeightEvent], None] | None = None,
                 on_removed: Callable[[WeightEvent], None] | None = None) -> None:
        self._cfg = config
        self._on_detected = on_detected or (lambda e: None)
        self._on_removed = on_removed or (lambda e: None)
        self._state = PackageState.IDLE
        self._reference_g: float = 0.0
        self._stable_since_ms: int | None = None
        self._candidate_g: float = 0.0

    @property
    def state(self) -> PackageState:
        return self._state

    def update(self, weight_g: float) -> None:
        now_ms = int(time.monotonic() * 1000)

        if self._state == PackageState.IDLE:
            self._detect_package(weight_g, now_ms)
        else:
            self._detect_removal(weight_g, now_ms)

    def _detect_package(self, w: float, now_ms: int) -> None:
        threshold = self._cfg.package_detect_threshold_g
        if w >= threshold:
            if self._stable_since_ms is None or abs(w - self._candidate_g) > self._cfg.drift_tolerance_g:
                self._stable_since_ms = now_ms
                self._candidate_g = w
            elif (now_ms - self._stable_since_ms) >= self._cfg.stable_duration_ms:
                self._reference_g = w
                self._state = PackageState.GUARD_MODE
                self._stable_since_ms = None
                event = WeightEvent(weight_g=w)
                log_event("package_detected", event)
                self._on_detected(event)
        else:
            self._stable_since_ms = None

    def _detect_removal(self, w: float, now_ms: int) -> None:
        remove_threshold = self._reference_g * self._cfg.package_remove_threshold_ratio
        if w < remove_threshold:
            if self._stable_since_ms is None or abs(w - self._candidate_g) > self._cfg.drift_tolerance_g:
                self._stable_since_ms = now_ms
                self._candidate_g = w
            elif (now_ms - self._stable_since_ms) >= self._cfg.stable_duration_ms:
                self._state = PackageState.IDLE
                self._stable_since_ms = None
                event = WeightEvent(weight_g=w, reference_g=self._reference_g)
                log_event("package_removed", event)
                self._on_removed(event)
        else:
            self._stable_since_ms = None
