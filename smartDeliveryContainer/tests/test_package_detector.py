import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.core.config import WeightConfig
from smart_delivery_container.core.package_detector import PackageDetector, PackageState


def _cfg(**kwargs):
    defaults = dict(
        sample_interval_ms=1,
        moving_average_size=1,
        package_detect_threshold_g=300,
        package_remove_threshold_ratio=0.6,
        stable_duration_ms=1,
        drift_tolerance_g=50,
        calibration_offset=0,
        calibration_scale=1,
    )
    defaults.update(kwargs)
    return WeightConfig(**defaults)


def test_package_detected_after_stable():
    detected = []
    det = PackageDetector(_cfg(), on_detected=detected.append)
    det.update(500.0)
    time.sleep(0.002)
    det.update(500.0)
    assert len(detected) == 1
    assert det.state == PackageState.GUARD_MODE


def test_no_event_below_threshold():
    detected = []
    det = PackageDetector(_cfg(), on_detected=detected.append)
    det.update(100.0)
    time.sleep(0.002)
    det.update(100.0)
    assert len(detected) == 0
    assert det.state == PackageState.IDLE


def test_package_removed_after_stable():
    removed = []
    det = PackageDetector(_cfg(), on_removed=removed.append)
    det.update(500.0)
    time.sleep(0.002)
    det.update(500.0)
    assert det.state == PackageState.GUARD_MODE
    det.update(0.0)
    time.sleep(0.002)
    det.update(0.0)
    assert len(removed) == 1
    assert det.state == PackageState.IDLE


def test_noise_does_not_trigger_removal():
    removed = []
    det = PackageDetector(_cfg(stable_duration_ms=500), on_removed=removed.append)
    det.update(500.0)
    time.sleep(0.002)
    det.update(500.0)
    det.update(0.0)
    assert len(removed) == 0
