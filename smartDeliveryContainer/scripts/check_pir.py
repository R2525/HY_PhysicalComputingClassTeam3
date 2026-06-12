#!/usr/bin/env python3
"""PIR 감지 단독 테스트 스크립트.

실제 GPIO:
    python3 scripts/check_pir.py

시뮬레이션:
    PIR_SAMPLE_INTERVAL_MS=1 PIR_COOLDOWN_MS=0 \\
    python3 scripts/check_pir.py --simulate 0,0,1,1,0,1 --max-ticks 6
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.core.config import PirConfig
from smart_delivery_container.core.pir_monitor import PirMonitor
from smart_delivery_container.sensors.pir_sensor import GpioPirSensor, SimulatedPirSensor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", help="쉼표로 구분된 0/1 시퀀스")
    parser.add_argument("--max-ticks", type=int, default=None)
    args = parser.parse_args()

    config = PirConfig()

    if args.simulate:
        seq = [int(x) for x in args.simulate.split(",")]
        sensor = SimulatedPirSensor(seq)
    else:
        sensor = GpioPirSensor(config.pin)

    monitor = PirMonitor(sensor, config)
    try:
        monitor.run(max_ticks=args.max_ticks)
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
