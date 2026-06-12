from __future__ import annotations
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

try:
    import cv2  # type: ignore[import]
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class CameraRecorder(ABC):
    @abstractmethod
    def capture_snapshot(self, event_id: str) -> Path: ...

    @abstractmethod
    def record_clip(self, event_id: str, seconds: int = 5) -> Path: ...

    def close(self) -> None:
        pass


class OpenCvCameraRecorder(CameraRecorder):
    def __init__(self, index: int, snapshot_dir: Path, video_dir: Path) -> None:
        if not _CV2_AVAILABLE:
            raise RuntimeError("opencv-python is not installed")
        self._cap = cv2.VideoCapture(index)
        self._snap_dir = Path(snapshot_dir)
        self._vid_dir = Path(video_dir)
        self._snap_dir.mkdir(parents=True, exist_ok=True)
        self._vid_dir.mkdir(parents=True, exist_ok=True)

    def capture_snapshot(self, event_id: str) -> Path:
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("카메라 프레임 읽기 실패")
        path = self._snap_dir / f"snapshot_{_ts()}_{event_id}.jpg"
        cv2.imwrite(str(path), frame)
        return path

    def record_clip(self, event_id: str, seconds: int = 5) -> Path:
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("카메라 프레임 읽기 실패")
        h, w = frame.shape[:2]
        path = self._vid_dir / f"clip_{_ts()}_{event_id}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        fps = 20.0
        writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ok, f = self._cap.read()
            if ok:
                writer.write(f)
        writer.release()
        return path

    def close(self) -> None:
        self._cap.release()


class NullCameraRecorder(CameraRecorder):
    """카메라 없는 환경에서 경로만 반환하는 더미 레코더."""

    def __init__(self, snapshot_dir: Path, video_dir: Path) -> None:
        self._snap_dir = Path(snapshot_dir)
        self._vid_dir = Path(video_dir)

    def capture_snapshot(self, event_id: str) -> Path:
        return self._snap_dir / f"snapshot_{_ts()}_{event_id}.jpg"

    def record_clip(self, event_id: str, seconds: int = 5) -> Path:
        return self._vid_dir / f"clip_{_ts()}_{event_id}.mp4"
