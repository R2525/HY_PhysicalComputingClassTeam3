from __future__ import annotations
import threading
import time
import os


class SpeakerAlarm:
    """GPIO PWM 기반 패시브 버저 / 스피커 경보음.

    pin.md: Speaker IN → 물리 핀 12 → BCM GPIO 18 (하드웨어 PWM 지원)
    """

    def __init__(self, pin: int = 18, frequency: int = 2000) -> None:
        self._pin = pin
        self._freq = frequency
        self._duty_cycle = float(os.getenv("SPEAKER_DUTY_CYCLE", "20"))
        self._pwm = None
        self._lock = threading.Lock()
        try:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            self._pwm = GPIO.PWM(pin, frequency)
            self._GPIO = GPIO
            print(f"[SPEAKER] 초기화 완료 — GPIO{pin}, {frequency}Hz")
        except Exception as e:
            print(f"[SPEAKER] 초기화 실패 (콘솔 모드): {e}")

    def beep(self, duration: float = 0.5, freq: int | None = None) -> None:
        """blocking — duration 초 동안 버저 울림."""
        with self._lock:
            if self._pwm is None:
                print(f"[SPEAKER] 🔔 beep {duration}s")
                time.sleep(duration)
                return
            if freq:
                self._pwm.ChangeFrequency(freq)
            self._pwm.start(self._duty_cycle)
            time.sleep(duration)
            self._pwm.stop()

    def pattern(self, count: int = 3, on: float = 0.3, off: float = 0.2,
                freq: int | None = None) -> None:
        """비블로킹 — 짧은 비프 count번 반복."""
        def _play():
            for i in range(count):
                self.beep(on, freq=freq)
                if i < count - 1:
                    time.sleep(off)
        threading.Thread(target=_play, daemon=True).start()

    def alarm(self) -> None:
        """비블로킹 — 경보 패턴."""
        def _play():
            for _ in range(3):
                self.beep(0.12, freq=1800)
                time.sleep(0.12)
                self.beep(0.12, freq=1000)
                time.sleep(0.08)
        threading.Thread(target=_play, daemon=True).start()

    def close(self) -> None:
        if self._pwm:
            try:
                self._pwm.stop()
                self._GPIO.cleanup([self._pin])
            except Exception:
                pass
