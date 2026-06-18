from __future__ import annotations
import time

from smart_delivery_container.sensors.pir_sensor import PirSensor


class HcSr04Sensor(PirSensor):
    """HC-SR04 초음파 거리 센서. threshold_cm 이내이면 감지(True) 반환."""

    _SOUND_CM_PER_US = 0.0343  # 20°C 기준 음속

    def __init__(self, trigger_pin: int, echo_pin: int,
                 threshold_cm: float = 20.0) -> None:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(trigger_pin, GPIO.OUT)
        GPIO.setup(echo_pin, GPIO.IN)
        GPIO.output(trigger_pin, False)
        time.sleep(0.05)  # 초기 안정화

        self._GPIO = GPIO
        self._trig = trigger_pin
        self._echo = echo_pin
        self._threshold = threshold_cm

    def measure_cm(self) -> float:
        """초음파 거리 측정 (cm). 타임아웃 시 999.0 반환."""
        GPIO = self._GPIO

        GPIO.output(self._trig, True)
        time.sleep(0.00001)   # 10μs 트리거 펄스
        GPIO.output(self._trig, False)

        deadline = time.monotonic() + 0.04
        while GPIO.input(self._echo) == 0:
            if time.monotonic() > deadline:
                return 999.0
        pulse_start = time.monotonic()

        deadline = time.monotonic() + 0.04
        while GPIO.input(self._echo) == 1:
            if time.monotonic() > deadline:
                return 999.0
        pulse_end = time.monotonic()

        duration_us = (pulse_end - pulse_start) * 1_000_000
        return duration_us / 2.0 * self._SOUND_CM_PER_US

    def motion_detected(self) -> bool:
        try:
            return self.measure_cm() <= self._threshold
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._GPIO.cleanup([self._trig, self._echo])
        except Exception:
            pass
