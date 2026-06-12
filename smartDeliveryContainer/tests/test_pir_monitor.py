import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.core.config import PirConfig
from smart_delivery_container.core.pir_monitor import PirEvent, PirMonitor
from smart_delivery_container.sensors.pir_sensor import SimulatedPirSensor


def _make_monitor(seq, cooldown_ms=0):
    cfg = PirConfig(pin=17, sample_interval_ms=1, cooldown_ms=cooldown_ms)
    sensor = SimulatedPirSensor(seq)
    events = []
    monitor = PirMonitor(sensor, cfg, on_motion=events.append)
    return monitor, events


def test_rising_edge_triggers_event():
    monitor, events = _make_monitor([0, 0, 1, 1, 0])
    for _ in range(5):
        monitor.tick()
    assert len(events) == 1


def test_no_event_when_signal_stays_low():
    monitor, events = _make_monitor([0, 0, 0])
    for _ in range(3):
        monitor.tick()
    assert len(events) == 0


def test_two_separate_motions():
    monitor, events = _make_monitor([0, 1, 0, 0, 1, 0], cooldown_ms=0)
    for _ in range(6):
        monitor.tick()
    assert len(events) == 2


def test_cooldown_suppresses_second_event():
    cfg = PirConfig(pin=17, sample_interval_ms=1, cooldown_ms=99999)
    sensor = SimulatedPirSensor([0, 1, 0, 1])
    events = []
    monitor = PirMonitor(sensor, cfg, on_motion=events.append)
    for _ in range(4):
        monitor.tick()
    assert len(events) == 1


def test_pir_event_has_pin():
    monitor, events = _make_monitor([0, 1])
    for _ in range(2):
        monitor.tick()
    assert events[0].pin == 17
