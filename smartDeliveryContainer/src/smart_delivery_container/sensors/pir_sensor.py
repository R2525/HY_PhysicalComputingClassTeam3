from __future__ import annotations
from abc import ABC, abstractmethod
from collections import deque


class PirSensor(ABC):
    @abstractmethod
    def motion_detected(self) -> bool: ...

    def close(self) -> None:
        pass


class GpioPirSensor(PirSensor):
    def __init__(self, pin: int) -> None:
        from gpiozero import MotionSensor  # type: ignore[import]
        self._sensor = MotionSensor(pin)

    def motion_detected(self) -> bool:
        return bool(self._sensor.motion_detected)

    def close(self) -> None:
        self._sensor.close()


class SimulatedPirSensor(PirSensor):
    """순서대로 0/1 값을 반환하는 테스트용 가짜 PIR 센서."""

    def __init__(self, sequence: list[int]) -> None:
        self._queue: deque[int] = deque(sequence)

    def motion_detected(self) -> bool:
        if not self._queue:
            return False
        return bool(self._queue.popleft())
