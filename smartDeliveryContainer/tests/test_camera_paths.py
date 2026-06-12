import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_delivery_container.camera.camera_recorder import NullCameraRecorder


def test_snapshot_path_contains_event_id(tmp_path):
    recorder = NullCameraRecorder(tmp_path / "snaps", tmp_path / "vids")
    path = recorder.capture_snapshot("evt001")
    assert "evt001" in path.name


def test_clip_path_contains_event_id(tmp_path):
    recorder = NullCameraRecorder(tmp_path / "snaps", tmp_path / "vids")
    path = recorder.record_clip("evt002")
    assert "evt002" in path.name


def test_snapshot_extension_is_jpg(tmp_path):
    recorder = NullCameraRecorder(tmp_path / "snaps", tmp_path / "vids")
    path = recorder.capture_snapshot("test")
    assert path.suffix == ".jpg"


def test_clip_extension_is_mp4(tmp_path):
    recorder = NullCameraRecorder(tmp_path / "snaps", tmp_path / "vids")
    path = recorder.record_clip("test")
    assert path.suffix == ".mp4"
