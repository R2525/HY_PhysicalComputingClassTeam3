import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.sensors.weight_filter import MovingAverageFilter


def test_single_value():
    f = MovingAverageFilter(3)
    assert f.update(100.0) == 100.0


def test_average_of_three():
    f = MovingAverageFilter(3)
    f.update(100.0)
    f.update(200.0)
    result = f.update(300.0)
    assert abs(result - 200.0) < 0.01


def test_sliding_window_drops_old():
    f = MovingAverageFilter(2)
    f.update(100.0)
    f.update(200.0)
    result = f.update(300.0)
    assert abs(result - 250.0) < 0.01


def test_not_ready_until_full():
    f = MovingAverageFilter(3)
    assert not f.ready
    f.update(1.0)
    assert not f.ready
    f.update(2.0)
    assert not f.ready
    f.update(3.0)
    assert f.ready
