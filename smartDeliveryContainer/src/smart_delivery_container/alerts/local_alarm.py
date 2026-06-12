from __future__ import annotations
import os

try:
    import serial  # type: ignore[import]
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False


class LocalAlarm:
    """DFPlayer Mini 시리얼 경보음 출력. 하드웨어 없으면 콘솔 출력으로 대체."""

    def __init__(self, port: str = "/dev/serial0", baudrate: int = 9600) -> None:
        self._ser = None
        if _SERIAL_AVAILABLE and os.path.exists(port):
            self._ser = serial.Serial(port, baudrate, timeout=1)

    def play(self, track: int = 1) -> None:
        if self._ser:
            cmd = bytes([0x7E, 0xFF, 0x06, 0x03, 0x00, 0x00, track, 0xEF])
            self._ser.write(cmd)
        else:
            print(f"[ALARM] 경보음 재생 (track={track})")

    def stop(self) -> None:
        if self._ser:
            cmd = bytes([0x7E, 0xFF, 0x06, 0x16, 0x00, 0x00, 0x00, 0xEF])
            self._ser.write(cmd)
        else:
            print("[ALARM] 경보음 중지")

    def close(self) -> None:
        if self._ser:
            self._ser.close()
