#!/usr/bin/env python3
"""ESP32-CAM MJPEG 스트림 뷰어.

사용법:
    python3 view_stream.py                        # 자동 IP 탐색
    python3 view_stream.py 192.168.x.x            # IP 직접 지정
    python3 view_stream.py 192.168.x.x --no-gui   # 터미널 출력만
"""
import sys
import urllib.request
import socket
import threading
import time

STREAM_PORT = 81
STREAM_PATH = "/stream"


def find_esp32_ip(subnet: str = "172.20.10") -> str | None:
    """서브넷에서 ESP32-CAM 스트림 응답하는 IP 탐색."""
    print(f"ESP32-CAM 탐색 중 ({subnet}.1 ~ .14)...")
    found = []

    def check(ip: str) -> None:
        try:
            url = f"http://{ip}:{STREAM_PORT}{STREAM_PATH}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1) as r:
                ct = r.headers.get("Content-Type", "")
                if "multipart" in ct:
                    found.append(ip)
        except Exception:
            pass

    threads = [threading.Thread(target=check, args=(f"{subnet}.{i}",)) for i in range(1, 15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return found[0] if found else None


def view_with_opencv(stream_url: str) -> None:
    try:
        import cv2
    except ImportError:
        print("opencv-python 없음. 설치: pip install opencv-python-headless")
        sys.exit(1)

    print(f"스트림 연결: {stream_url}")
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print("스트림 열기 실패")
        sys.exit(1)

    print("스트림 시작 (q 키로 종료)")
    while True:
        ok, frame = cap.read()
        if not ok:
            print("프레임 수신 실패")
            break
        cv2.imshow("ESP32-CAM Stream", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def view_terminal(stream_url: str) -> None:
    """GUI 없이 프레임 수신 확인만."""
    print(f"스트림 연결: {stream_url}")
    try:
        req = urllib.request.Request(stream_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            count = 0
            buf = b""
            start = time.time()
            while count < 30:
                buf += resp.read(4096)
                frames = buf.split(b"\xff\xd8")
                for chunk in frames[1:]:
                    end = chunk.find(b"\xff\xd9")
                    if end != -1:
                        count += 1
                        fps = count / (time.time() - start)
                        print(f"\r프레임 {count:3d} | {fps:.1f} fps", end="", flush=True)
                        buf = chunk[end + 2:]
                        break
            print(f"\n30 프레임 수신 완료 — 스트림 정상 동작 중")
    except Exception as e:
        print(f"오류: {e}")


def main() -> None:
    no_gui = "--no-gui" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        ip = args[0]
    else:
        ip = find_esp32_ip()
        if not ip:
            print("ESP32-CAM을 찾을 수 없습니다. ESP32-CAM이 WiFi에 연결됐는지 확인하세요.")
            print("직접 지정: python3 view_stream.py <IP주소>")
            sys.exit(1)
        print(f"발견: {ip}")

    stream_url = f"http://{ip}:{STREAM_PORT}{STREAM_PATH}"
    print(f"스트림 URL: {stream_url}")

    if no_gui:
        view_terminal(stream_url)
    else:
        view_with_opencv(stream_url)


if __name__ == "__main__":
    main()
