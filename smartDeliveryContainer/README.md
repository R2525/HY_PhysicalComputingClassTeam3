# SmartDeliveryContainer

택배 도난 방지 시스템. 라즈베리 파이 + 로컬 카메라 + HC-SR04 + HX711 로드셀 + 스피커 + 텔레그램 알람으로 구성.

---

## 하드웨어 구성

### 핀 배선 (pin.md 기준)

| 모듈 | 핀 이름 | 물리 핀 | BCM GPIO |
|------|---------|---------|----------|
| HX711 (로드셀) | VCC | 1 | 3.3V |
| | GND | 6 | GND |
| | DT | 29 | GPIO 5 |
| | SCK | 31 | GPIO 6 |
| HC-SR04 (초음파) | VCC | 2 | 5V |
| | GND | 14 | GND |
| | TRIG | 16 | GPIO 23 |
| | ECHO | 18 | GPIO 24 |
| 스피커 (버저) | VCC | 4 | 5V |
| | GND | 20 | GND |
| | IN | 12 | GPIO 18 (PWM) |
| Raspberry Pi Camera/USB Camera | — | CSI 또는 USB | 로컬 카메라 |

### 아키텍처

```
라즈베리 파이
├── HX711 (GPIO 5/6)         ← 로드셀 무게 측정
├── HC-SR04 (GPIO 23/24)     ← 20cm 이내 접근 감지
├── Speaker (GPIO 18 PWM)    ← 경보음
└── Local Camera (/dev/video0) ← 로컬 카메라 캡처/녹화
         ↕
    텔레그램 Bot API           ← 원격 알림 + 사진 전송
```

---

## 동작 흐름

```
HC-SR04 20cm 이내 감지
    → 로컬 카메라 버퍼링 시작

HX711 무게 변화율 임계값 초과
    → 텔레그램 알림
    → 스피커 경보음 (고저 교차 패턴)
    → 이벤트 전 30초 + 후 10초 클립 녹화
    → 텔레그램으로 영상 전송
```

---

## 설치

```bash
# 의존성 설치
pip install hx711 flask opencv-python-headless RPi.GPIO gpiozero

# 설정 파일 생성
cp config/settings.example.env config/.env
```

---

## 설정 (`config/.env`)

```env
# HX711 로드셀
HX711_DOUT_PIN=5
HX711_SCK_PIN=6
CALIBRATION_OFFSET=0       # 캘리브레이션 후 조정
CALIBRATION_SCALE=1        # 캘리브레이션 후 조정
PACKAGE_DETECT_THRESHOLD_G=300

# HC-SR04 초음파
HCSR04_TRIGGER_PIN=23
HCSR04_ECHO_PIN=24
HCSR04_THRESHOLD_CM=20.0

# 스피커
SPEAKER_PIN=18
SPEAKER_FREQUENCY=2000

# 텔레그램 Bot (https://t.me/BotFather 에서 발급)
TELEGRAM_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# 라즈베리파이에 직접 연결된 카메라
CAMERA_INDEX=0
```

### 텔레그램 Bot 설정 방법

1. 텔레그램에서 `@BotFather` 검색 → `/newbot` 명령으로 Bot 생성
2. 발급된 **Token**을 `TELEGRAM_TOKEN`에 입력
3. `@userinfobot` 에서 본인 Chat ID 확인 → `TELEGRAM_CHAT_ID`에 입력

---

## 실행

```bash
cd smartDeliveryContainer
python3 -u scripts/run_system.py
```

### 로드셀 캘리브레이션

```bash
python3 scripts/calibrate_weight.py
# 출력된 offset / scale 값을 config/.env에 입력
```

---

## 카메라 확인

```bash
python3 scripts/check_camera.py
```

`CAMERA_INDEX=0`은 보통 `/dev/video0`을 의미합니다. 다른 장치로 잡히면 `config/.env`의 `CAMERA_INDEX`를 변경하세요.

---

## 프로젝트 구조

```
smartDeliveryContainer/
├── config/
│   ├── .env                    # 실제 설정 (git 제외)
│   └── settings.example.env    # 설정 예시
├── scripts/
│   ├── run_system.py           # 메인 실행
│   ├── calibrate_weight.py     # 로드셀 캘리브레이션
│   └── check_camera.py         # 카메라 연결 확인
├── src/smart_delivery_container/
│   ├── alerts/
│   │   ├── speaker_alarm.py    # GPIO PWM 스피커
│   │   ├── telegram_notifier.py# 텔레그램 Bot 알람
│   │   └── local_alarm.py      # DFPlayer 시리얼 (대체 방식)
│   ├── camera/
│   │   └── camera_recorder.py  # 로컬 카메라 / Null 레코더
│   ├── core/
│   │   ├── config.py           # 전체 설정 dataclass
│   │   ├── package_detector.py # 무게 기반 택배 감지 상태머신
│   │   ├── pir_monitor.py      # 모션/근접 감지 모니터 (HC-SR04 재사용)
│   │   └── weight_monitor.py   # HX711 무게 모니터
│   └── sensors/
│       ├── hcsr04_sensor.py    # HC-SR04 초음파 거리 센서
│       ├── weight_sensor.py    # HX711 로드셀 센서
│       └── pir_sensor.py       # PirSensor 추상 인터페이스
└── data/
    ├── snapshots/              # 접근 감지 시 스냅샷
    ├── videos/                 # 도난 확정 시 클립
    └── events/events.jsonl     # 이벤트 로그
```

---

## 알려진 이슈

| 증상 | 원인 | 해결 |
|------|------|------|
| 카메라 열기 실패 | `CAMERA_INDEX` 불일치 또는 카메라 권한 문제 | `/dev/video*` 확인 후 `CAMERA_INDEX` 수정 |
| HX711 `reset()` 블로킹 | 이전 프로세스 GPIO 점유 | `python3 -c "import RPi.GPIO as GPIO; GPIO.cleanup()"` 실행 후 재시작 |
| HC-SR04 항상 999cm | 배선 오류 또는 전원 부족 | TRIG=GPIO23(물리16), ECHO=GPIO24(물리18) 재확인 |
| 텔레그램 전송 실패 | Token/Chat ID 미설정 | `config/.env`에 값 입력 |
