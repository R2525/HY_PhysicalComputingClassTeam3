from __future__ import annotations
import threading
import time
import subprocess
from abc import ABC, abstractmethod
from collections import deque
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


class OpenCvBufferedRecorder:
    """라즈베리파이에 직접 연결된 카메라를 롤링 버퍼로 유지한다."""

    def __init__(self, index: int, video_dir: Path,
                 buffer_seconds: float = 30.0,
                 post_event_seconds: float = 10.0,
                 fps: float = 10.0) -> None:
        if not _CV2_AVAILABLE:
            raise RuntimeError("opencv-python is not installed")
        self._index = index
        self._vid_dir = Path(video_dir)
        self._vid_dir.mkdir(parents=True, exist_ok=True)
        self._buffer_seconds = buffer_seconds
        self._post_event_seconds = post_event_seconds
        self._fps = fps
        self._buf: deque[tuple[float, object]] = deque()
        self._lock = threading.Lock()
        self._active = False
        self._thread: threading.Thread | None = None
        self._cap = None

    def start_buffering(self) -> None:
        self._active = True
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()

    def stop_buffering(self) -> None:
        self._active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_buffering(self) -> bool:
        return self._active and (self._thread is not None and self._thread.is_alive())

    @property
    def buffered_seconds(self) -> float:
        with self._lock:
            if len(self._buf) < 2:
                return 0.0
            return self._buf[-1][0] - self._buf[0][0]

    def save_event_clip(self, event_id: str, on_done=None) -> None:
        """무게 이벤트 발생 시 비블로킹으로 영상 저장."""
        event_time = time.monotonic()
        threading.Thread(
            target=self._save_clip,
            args=(event_id, event_time, on_done),
            daemon=True,
        ).start()

    def _save_clip(self, event_id: str, event_time: float, on_done) -> None:
        end_time = event_time + self._post_event_seconds
        while time.monotonic() < end_time:
            time.sleep(0.1)

        with self._lock:
            frames = [
                (ts, frame.copy()) for ts, frame in self._buf
                if ts >= event_time - self._buffer_seconds
            ]

        if not frames:
            print("[CAM] 저장할 프레임 없음")
            return

        first = frames[0][1]
        h, w = first.shape[:2]
        path = self._vid_dir / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{event_id}.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), self._fps, (w, h))
        for _, frame in frames:
            if frame.shape[:2] != (h, w):
                frame = cv2.resize(frame, (w, h))
            writer.write(frame)
        writer.release()
        print(f"[CAM] 영상 저장 완료: {path.name} ({len(frames)} 프레임)")
        if on_done:
            on_done(path)

    def _read_loop(self) -> None:
        try:
            self._cap = cv2.VideoCapture(self._index)
            if not self._cap.isOpened():
                raise RuntimeError(f"카메라 열기 실패: index={self._index}")

            frame_interval = 1.0 / self._fps if self._fps > 0 else 0.0
            next_frame_at = time.monotonic()

            while self._active:
                ok, frame = self._cap.read()
                if not ok:
                    print("[CAM] 카메라 프레임 읽기 실패, 재시도 중...")
                    time.sleep(0.5)
                    continue

                now = time.monotonic()
                if now < next_frame_at:
                    time.sleep(next_frame_at - now)
                    continue
                next_frame_at = now + frame_interval

                cutoff = now - self._buffer_seconds
                with self._lock:
                    self._buf.append((now, frame.copy()))
                    while self._buf and self._buf[0][0] < cutoff:
                        self._buf.popleft()
        except Exception as e:
            if self._active:
                print(f"[CAM] 로컬 카메라 오류: {e}")
        finally:
            if self._cap is not None:
                self._cap.release()
                self._cap = None


class RpiCamBufferedRecorder:
    """rpicam-vid로 Raspberry Pi CSI 카메라 MJPEG 프레임을 버퍼링한다."""

    _SOI = b"\xff\xd8"
    _EOI = b"\xff\xd9"

    def __init__(self, video_dir: Path,
                 buffer_seconds: float = 30.0,
                 post_event_seconds: float = 10.0,
                 fps: float = 10.0,
                 width: int = 640,
                 height: int = 480) -> None:
        if not _CV2_AVAILABLE:
            raise RuntimeError("opencv-python is not installed")
        self._vid_dir = Path(video_dir)
        self._vid_dir.mkdir(parents=True, exist_ok=True)
        self._buffer_seconds = buffer_seconds
        self._post_event_seconds = post_event_seconds
        self._fps = fps
        self._width = width
        self._height = height
        self._buf: deque[tuple[float, bytes]] = deque()
        self._lock = threading.Lock()
        self._active = False
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[bytes] | None = None

    def start_buffering(self) -> None:
        self._active = True
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()

    def stop_buffering(self) -> None:
        self._active = False
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    @property
    def is_buffering(self) -> bool:
        return self._active and (self._thread is not None and self._thread.is_alive())

    @property
    def buffered_seconds(self) -> float:
        with self._lock:
            if len(self._buf) < 2:
                return 0.0
            return self._buf[-1][0] - self._buf[0][0]

    def save_event_clip(self, event_id: str, on_done=None) -> None:
        event_time = time.monotonic()
        threading.Thread(
            target=self._save_clip,
            args=(event_id, event_time, on_done),
            daemon=True,
        ).start()

    def _save_clip(self, event_id: str, event_time: float, on_done) -> None:
        import numpy as np

        end_time = event_time + self._post_event_seconds
        while time.monotonic() < end_time:
            time.sleep(0.1)

        with self._lock:
            frames = [
                (ts, jpeg) for ts, jpeg in self._buf
                if ts >= event_time - self._buffer_seconds
            ]

        if not frames:
            print("[CAM] 저장할 프레임 없음")
            return

        first = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
        if first is None:
            print("[CAM] 첫 프레임 디코딩 실패")
            return

        h, w = first.shape[:2]
        path = self._vid_dir / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{event_id}.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), self._fps, (w, h))
        writer.write(first)
        for _, jpeg in frames[1:]:
            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            if frame.shape[:2] != (h, w):
                frame = cv2.resize(frame, (w, h))
            writer.write(frame)
        writer.release()
        print(f"[CAM] 영상 저장 완료: {path.name} ({len(frames)} 프레임)")
        if on_done:
            on_done(path)

    def _read_loop(self) -> None:
        cmd = [
            "rpicam-vid",
            "--timeout", "0",
            "--codec", "mjpeg",
            "--width", str(self._width),
            "--height", str(self._height),
            "--framerate", str(int(self._fps)),
            "--nopreview",
            "--output", "-",
        ]
        while self._active:
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                if self._proc.stdout is None:
                    raise RuntimeError("rpicam-vid stdout 연결 실패")

                raw = b""
                print("[CAM] rpicam 버퍼링 시작")
                while self._active:
                    chunk = self._proc.stdout.read(4096)
                    if not chunk:
                        raise RuntimeError("rpicam-vid 출력 종료")
                    raw += chunk
                    while True:
                        s = raw.find(self._SOI)
                        if s == -1:
                            raw = raw[-1:]
                            break
                        e = raw.find(self._EOI, s)
                        if e == -1:
                            raw = raw[s:]
                            break
                        jpeg = raw[s:e + 2]
                        raw = raw[e + 2:]
                        now = time.monotonic()
                        cutoff = now - self._buffer_seconds
                        with self._lock:
                            self._buf.append((now, jpeg))
                            while self._buf and self._buf[0][0] < cutoff:
                                self._buf.popleft()
            except Exception as e:
                if self._active:
                    print(f"[CAM] rpicam 오류: {e}, 재시도 중...")
                    time.sleep(2)
            finally:
                if self._proc is not None and self._proc.poll() is None:
                    self._proc.terminate()
                self._proc = None
