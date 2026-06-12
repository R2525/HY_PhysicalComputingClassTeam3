#!/usr/bin/env python3
"""로드셀 HX711 보정 스크립트.

    python3 scripts/calibrate_weight.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.core.config import WeightConfig
from smart_delivery_container.sensors.weight_sensor import HX711WeightSensor


def main() -> None:
    cfg = WeightConfig()
    sensor = HX711WeightSensor(cfg.hx711_dout_pin, cfg.hx711_sck_pin)

    print("=== 로드셀 보정 ===")
    input("아무것도 올리지 않은 상태에서 Enter...")
    zero_vals = [sensor.read_grams() for _ in range(20)]
    offset = sum(zero_vals) / len(zero_vals)
    print(f"영점 raw 평균: {offset:.2f}")

    known_g = float(input("기준 추 무게(g)를 입력하세요: "))
    input(f"{known_g}g 추를 올린 뒤 Enter...")
    weight_vals = [sensor.read_grams() for _ in range(20)]
    raw_mean = sum(weight_vals) / len(weight_vals)
    scale = (raw_mean - offset) / known_g
    print(f"\n.env 에 추가하세요:")
    print(f"CALIBRATION_OFFSET={offset:.4f}")
    print(f"CALIBRATION_SCALE={scale:.4f}")


if __name__ == "__main__":
    main()
