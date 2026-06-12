from __future__ import annotations
from collections import deque


class MovingAverageFilter:
    def __init__(self, size: int) -> None:
        self._size = max(1, size)
        self._buf: deque[float] = deque(maxlen=self._size)

    def update(self, value: float) -> float:
        self._buf.append(value)
        return sum(self._buf) / len(self._buf)

    @property
    def ready(self) -> bool:
        return len(self._buf) == self._size
