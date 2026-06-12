from __future__ import annotations
from abc import ABC, abstractmethod
from collections import deque


class WeightSensor(ABC):
    @abstractmethod
    def read_grams(self) -> float: ...

    def close(self) -> None:
        pass


class HX711WeightSensor(WeightSensor):
    def __init__(self, dout_pin: int, sck_pin: int,
                 offset: float = 0, scale: float = 1) -> None:
        from hx711 import HX711  # type: ignore[import]
        self._hx = HX711(dout_pin, sck_pin)
        self._hx.reset()
        self._offset = offset
        self._scale = scale

    def read_grams(self) -> float:
        data = self._hx.get_raw_data(times=5)
        if not data:
            return 0.0
        raw = sum(data) / len(data)
        return (float(raw) - self._offset) / self._scale


class SimulatedWeightSensor(WeightSensor):
    """순서대로 그램값을 반환하는 테스트용 가짜 무게 센서."""

    def __init__(self, sequence: list[float]) -> None:
        self._queue: deque[float] = deque(sequence)
        self._last: float = 0.0

    def read_grams(self) -> float:
        if self._queue:
            self._last = self._queue.popleft()
        return self._last
