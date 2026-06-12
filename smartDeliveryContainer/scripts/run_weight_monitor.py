#!/usr/bin/env python3
"""무게 감지 단독 테스트 스크립트.

실제 HX711:
    python3 scripts/run_weight_monitor.py

시뮬레이션:
    SAMPLE_INTERVAL_MS=1 MOVING_AVERAGE_SIZE=1 STABLE_DURATION_MS=3 \\
    python3 scripts/run_weight_monitor.py \\
      --simulate 0,0,0,500,500,500,500,500,0,0,0,0,0 \\
      --max-ticks 13
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.core.config import WeightConfig
from smart_delivery_container.core.weight_monitor import WeightMonitor
from smart_delivery_container.sensors.weight_sensor import HX711WeightSensor, SimulatedWeightSensor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", help="쉼표로 구분된 그램값 시퀀스")
    parser.add_argument("--max-ticks", type=int, default=None)
    args = parser.parse_args()

    cfg = WeightConfig()

    if args.simulate:
        seq = [float(x) for x in args.simulate.split(",")]
        sensor = SimulatedWeightSensor(seq)
    else:
        sensor = HX711WeightSensor(cfg.hx711_dout_pin, cfg.hx711_sck_pin,
                                   cfg.calibration_offset, cfg.calibration_scale)

    monitor = WeightMonitor(sensor, cfg)
    try:
        monitor.run(max_ticks=args.max_ticks)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
