from __future__ import annotations
import json
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class TelegramNotifier:
    """Telegram Bot API로 메시지 및 사진 전송.

    token / chat_id 미설정 시 콘솔 출력으로 대체.
    """

    _API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = str(chat_id)
        self._enabled = bool(token and chat_id)
        if not self._enabled:
            print("[TELEGRAM] 토큰/채팅ID 미설정 — 콘솔 출력 모드")

    # ── public ────────────────────────────────────────────────────────────
    def send(self, event_type: str, payload: dict | None = None) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"🚨 *{event_type}*", f"🕐 {ts}"]
        if payload:
            for k, v in payload.items():
                lines.append(f"• {k}: {v}")
        msg = "\n".join(lines)
        if self._enabled:
            threading.Thread(target=self._post_message, args=(msg,), daemon=True).start()
        else:
            print(f"[TELEGRAM] {msg}")

    def send_video(self, video_path: Path | str, caption: str = "") -> None:
        path = Path(video_path)
        if not path.exists():
            print(f"[TELEGRAM] 영상 없음: {path}")
            return
        if self._enabled:
            threading.Thread(target=self._post_video, args=(path, caption), daemon=True).start()
        else:
            print(f"[TELEGRAM] 🎥 영상 전송: {path.name}  caption={caption}")

    def send_photo(self, image_path: Path | str, caption: str = "") -> None:
        path = Path(image_path)
        if not path.exists():
            print(f"[TELEGRAM] 사진 없음: {path}")
            return
        if self._enabled:
            threading.Thread(target=self._post_photo, args=(path, caption), daemon=True).start()
        else:
            print(f"[TELEGRAM] 📸 사진 전송: {path.name}  caption={caption}")

    def close(self) -> None:
        pass

    # ── private ───────────────────────────────────────────────────────────
    def _url(self, method: str) -> str:
        return self._API.format(token=self._token, method=method)

    def _post_message(self, text: str) -> None:
        data = json.dumps({
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(
            self._url("sendMessage"), data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8):
                pass
        except Exception as e:
            print(f"[TELEGRAM] 메시지 전송 실패: {e}")

    def _post_video(self, path: Path, caption: str) -> None:
        self._post_file(path, caption, field="video", method="sendVideo", timeout=180)

    def _post_photo(self, path: Path, caption: str) -> None:
        self._post_file(path, caption, field="photo", method="sendPhoto", timeout=15)

    def _post_file(self, path: Path, caption: str, field: str, method: str, timeout: int) -> None:
        boundary = "TGBound"
        buf = bytearray()
        mime = "video/mp4" if field == "video" else "image/jpeg"

        def part(name: str, value: bytes, filename: str = "") -> None:
            disp = f'form-data; name="{name}"'
            if filename:
                disp += f'; filename="{filename}"'
            buf.extend(f"--{boundary}\r\n".encode())
            buf.extend(f"Content-Disposition: {disp}\r\n".encode())
            if filename:
                buf.extend(f"Content-Type: {mime}\r\n".encode())
            buf.extend(b"\r\n")
            buf.extend(value)
            buf.extend(b"\r\n")

        part("chat_id", self._chat_id.encode())
        if caption:
            part("caption", caption.encode())
        part(field, path.read_bytes(), filename=path.name)
        buf.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            self._url(method), data=bytes(buf),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout):
                pass
        except Exception as e:
            print(f"[TELEGRAM] {field} 전송 실패: {e}")
