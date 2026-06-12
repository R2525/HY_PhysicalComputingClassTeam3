# From Scratch Implementation Guide

이 문서는 새 환경에서 `smartDeliveryContainer` 프로젝트를 처음부터 다시 만든다는 전제로 작성한다. 기존 코드가 없다고 가정하고, 디렉터리 생성, 라이브러리 설치, PIR 감지, 카메라 녹화, 무게 감지, 도난 판단 연결 순서대로 구현한다.

## 1. 구현 목표

현관 앞 택배 보관 매트에 센서와 카메라를 연결해 다음 흐름을 구현한다.

```text
시스템 시작
  -> 센서/카메라/로그 초기화
  -> PIR 24시간 감시
  -> 움직임 감지 시 로그 출력
  -> 카메라 스냅샷 또는 영상 저장
  -> 로드셀 무게 감시
  -> 택배가 놓이면 보관 모드 진입
  -> 보관 중 무게가 줄면 도난 후보 이벤트 발생
  -> PIR 움직임 + 무게 감소가 함께 확인되면 도난 이벤트 확정
  -> 영상 저장, 현장 경보, 스마트폰 알림
  -> 이벤트 로그 저장
```

처음부터 모두 만들 때는 한 번에 통합하지 않는다. 아래 순서대로 하나씩 완성한다.

1. 프로젝트 구조 생성
2. 설정/로그 공통 모듈 구현
3. PIR 감지 구현
4. 카메라 스냅샷/녹화 구현
5. 로드셀/HX711 무게 감지 구현
6. 도난 판단 상태 머신 구현
7. 알림/경보 구현
8. 전체 실행 스크립트 연결

## 2. 하드웨어 기준

| 모듈 | 역할 | 우선순위 |
| --- | --- | --- |
| Raspberry Pi | 전체 제어 장치 | 필수 |
| PIR 센서 | 사람 접근/움직임 감지 | 1차 테스트 |
| USB 웹캠 또는 Pi Camera | 스냅샷/영상 저장 | 2차 테스트 |
| 로드셀 + HX711 | 택배 적재/제거 감지 | 핵심 기능 |
| DFPlayer Mini + 스피커 | 현장 경보음 출력 | 선택 |
| MQTT/FCM | 스마트폰 알림 | 선택 |

현재 하드웨어가 PIR뿐이라면 먼저 PIR 감지와 로그 출력까지만 완성한다.

## 3. 프로젝트 디렉터리

빈 프로젝트에서 다음 구조를 만든다.

```text
smartDeliveryContainer/
  config/
    settings.example.env
  data/
    events/
    snapshots/
    videos/
  doc/
    implements/
  logs/
  scripts/
  src/
    smart_delivery_container/
      __init__.py
      alerts/
        __init__.py
      camera/
        __init__.py
      core/
        __init__.py
      sensors/
        __init__.py
      utils/
        __init__.py
  tests/
  requirements.txt
  requirements-raspi.txt
  pyproject.toml
  .gitignore
```

각 디렉터리 역할은 다음과 같다.

| 디렉터리 | 역할 |
| --- | --- |
| `config/` | GPIO 핀, 임계값, 카메라, MQTT 설정 |
| `data/events/` | 이벤트 로그 JSONL 저장 |
| `data/snapshots/` | 카메라 스냅샷 저장 |
| `data/videos/` | 이벤트 영상 저장 |
| `logs/` | 실행 로그 저장 |
| `scripts/` | 실행/점검/보정 스크립트 |
| `src/smart_delivery_container/sensors/` | PIR, 로드셀 등 센서 코드 |
| `src/smart_delivery_container/camera/` | 카메라 캡처/녹화 코드 |
| `src/smart_delivery_container/core/` | 설정, 상태 머신, 전체 흐름 |
| `src/smart_delivery_container/alerts/` | 경보음, MQTT/FCM 알림 |
| `src/smart_delivery_container/utils/` | 이벤트 로그, 파일명 생성 등 공통 유틸 |
| `tests/` | 센서 없는 환경에서 실행 가능한 테스트 |

## 4. 라이브러리 설치

### 4.1 공통 개발 환경

`requirements.txt`:

```text
numpy>=1.26,<3
opencv-python>=4.9,<5
paho-mqtt>=2.0,<3
python-dotenv>=1.0,<2
pytest>=8.0,<9
```

설치:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 Raspberry Pi 환경

`requirements-raspi.txt`:

```text
-r requirements.txt

gpiozero>=2.0,<3
lgpio>=0.2.2,<1
RPi.GPIO>=0.7,<1
hx711-rpi-py>=1.0,<2
pyserial>=3.5,<4
```

Raspberry Pi에서는 GPIO 관련 패키지를 먼저 설치한다.

```bash
sudo apt update
sudo apt install python3-gpiozero python3-lgpio
pip install -r requirements-raspi.txt
```

## 5. 설정 파일

`config/settings.example.env`를 만든다.

```text
HX711_DOUT_PIN=5
HX711_SCK_PIN=6
PIR_PIN=17

PIR_SAMPLE_INTERVAL_MS=100
PIR_COOLDOWN_MS=2000

SAMPLE_INTERVAL_MS=100
MOVING_AVERAGE_SIZE=10
PACKAGE_DETECT_THRESHOLD_G=300
PACKAGE_REMOVE_THRESHOLD_RATIO=0.6
STABLE_DURATION_MS=1500
DRIFT_TOLERANCE_G=50
CALIBRATION_OFFSET=0
CALIBRATION_SCALE=1

CAMERA_INDEX=0
VIDEO_OUTPUT_DIR=data/videos
SNAPSHOT_OUTPUT_DIR=data/snapshots
EVENT_OUTPUT_DIR=data/events

MQTT_HOST=
MQTT_PORT=1883
MQTT_TOPIC=smart-delivery/events

DFPLAYER_SERIAL_PORT=/dev/serial0
DFPLAYER_BAUDRATE=9600
```

실행 환경에서는 이 파일을 복사해서 `config/.env` 또는 프로젝트 루트 `.env`로 사용한다.

## 6. 공통 설정 모듈

먼저 `src/smart_delivery_container/core/config.py`를 만든다.

책임:

- `.env` 파일 로드
- 환경변수를 Python 설정 객체로 변환
- PIR, 무게 감지, 카메라, 이벤트 저장 위치 설정 제공

필요 클래스:

| 클래스 | 역할 |
| --- | --- |
| `PirConfig` | PIR 샘플링 주기, cooldown 설정 |
| `WeightConfig` | 무게 감지 임계값, 필터 크기, 보정값 |
| `CameraConfig` | 카메라 번호, 저장 경로, 녹화 시간 |
| `RuntimeConfig` | 전체 설정 묶음 |

구현 규칙:

- 환경변수가 없으면 기본값을 사용한다.
- `.env`가 없어도 실행되어야 한다.
- 숫자 설정은 `int` 또는 `float`로 변환한다.

## 7. 공통 이벤트 로그

`src/smart_delivery_container/utils/event_log.py`를 만든다.

책임:

- 이벤트를 `data/events/events.jsonl`에 한 줄 JSON으로 저장한다.
- 모든 이벤트에 `created_at` UTC 시간을 붙인다.
- dataclass, dict 모두 저장 가능해야 한다.

이벤트 예시:

```json
{"event_type":"pir_motion_detected","pin":17,"created_at":"2026-05-29T00:00:00+00:00"}
```

완료 기준:

- 이벤트가 발생할 때 콘솔에도 출력된다.
- 같은 이벤트가 파일에도 저장된다.
- 프로그램을 재실행해도 기존 로그 뒤에 append된다.

## 8. 1단계: PIR 감지 구현

가장 먼저 구현할 기능이다. PIR 센서는 24시간 켜져 있고, 움직임이 감지되면 로그를 찍는다.

### 8.1 파일

```text
src/smart_delivery_container/sensors/pir_sensor.py
src/smart_delivery_container/core/pir_monitor.py
scripts/check_pir.py
tests/test_pir_monitor.py
```

### 8.2 `pir_sensor.py`

필요 클래스:

| 클래스 | 역할 |
| --- | --- |
| `PirSensor` | PIR 센서 인터페이스 |
| `GpioPirSensor` | Raspberry Pi GPIO 실제 PIR 센서 |
| `SimulatedPirSensor` | 개발 PC 테스트용 가짜 PIR 센서 |

동작:

```text
GpioPirSensor.motion_detected()
  -> gpiozero.MotionSensor(pin).motion_detected 반환

SimulatedPirSensor.motion_detected()
  -> 미리 받은 0/1 시퀀스를 하나씩 반환
```

### 8.3 `pir_monitor.py`

필요 클래스:

| 클래스 | 역할 |
| --- | --- |
| `PirEvent` | PIR 이벤트 데이터 |
| `PirMonitor` | PIR 값을 주기적으로 읽고 이벤트 발생 |

이벤트 발생 조건:

```text
이전 값: False
현재 값: True
cooldown 시간이 지남
  -> pir_motion_detected 이벤트 발생
```

이렇게 rising edge에서만 이벤트를 발생시켜야 한다. PIR 신호가 몇 초 동안 계속 True로 유지되더라도 같은 움직임에 대해 로그가 계속 찍히면 안 된다.

### 8.4 `check_pir.py`

실제 Raspberry Pi 실행:

```bash
python3 scripts/check_pir.py
```

시뮬레이션 실행:

```bash
PIR_SAMPLE_INTERVAL_MS=1 PIR_COOLDOWN_MS=0 \
python3 scripts/check_pir.py --simulate 0,0,1,1,0,1 --max-ticks 6
```

기대 출력:

```text
PIR monitor started on GPIO 17
pir_motion_detected: pin=17 now_ms=...
pir_motion_detected: pin=17 now_ms=...
```

## 9. 2단계: 카메라 구현

PIR 로그가 정상적으로 찍힌 뒤 카메라를 연결한다.

### 9.1 파일

```text
src/smart_delivery_container/camera/camera_recorder.py
scripts/check_camera.py
tests/test_camera_paths.py
```

### 9.2 기능

| 기능 | 설명 |
| --- | --- |
| 스냅샷 저장 | PIR 감지 시 현재 프레임을 JPG로 저장 |
| 짧은 영상 저장 | PIR 감지 시 5~20초 영상 저장 |
| 파일명 생성 | 날짜와 이벤트 타입을 포함한 파일명 생성 |

### 9.3 카메라 인터페이스

`CameraRecorder`가 가져야 할 메서드:

```text
capture_snapshot(event_id) -> snapshot_path
record_clip(event_id, seconds) -> video_path
```

저장 위치:

```text
data/snapshots/
data/videos/
```

PIR과 카메라를 연결하면 흐름은 다음과 같다.

```text
PIR 감지
  -> pir_motion_detected 로그
  -> capture_snapshot()
  -> snapshot_saved 로그
```

이 단계에서는 아직 도난 판단을 하지 않는다. 단순히 움직임이 감지되면 카메라가 정상 동작하는지 확인한다.

## 10. 3단계: 무게 감지 구현

카메라까지 확인한 뒤 로드셀/HX711을 구현한다.

### 10.1 파일

```text
src/smart_delivery_container/sensors/weight_sensor.py
src/smart_delivery_container/sensors/weight_filter.py
src/smart_delivery_container/core/package_detector.py
src/smart_delivery_container/core/weight_monitor.py
scripts/calibrate_weight.py
scripts/run_weight_monitor.py
tests/test_weight_filter.py
tests/test_package_detector.py
```

### 10.2 무게 감지 흐름

```text
HX711 원시값 읽기
  -> 영점 보정 offset 적용
  -> scale로 gram 변환
  -> 이동평균 필터 적용
  -> 택배 적재 판단
  -> 보관 모드 진입
  -> 무게 감소 판단
  -> package_removed 이벤트 발생
```

### 10.3 상태

```text
IDLE
  택배 없음

GUARD_MODE
  택배가 놓여 보관 중
```

### 10.4 이벤트

| 이벤트 | 조건 |
| --- | --- |
| `package_detected` | 무게가 `PACKAGE_DETECT_THRESHOLD_G` 이상으로 `STABLE_DURATION_MS` 동안 유지 |
| `package_removed` | 보관 무게 대비 `PACKAGE_REMOVE_THRESHOLD_RATIO` 이상 감소가 `STABLE_DURATION_MS` 동안 유지 |

## 11. 4단계: PIR + 카메라 연결

PIR과 카메라가 각각 동작하면 둘을 연결한다.

파일:

```text
src/smart_delivery_container/core/pir_camera_monitor.py
scripts/run_pir_camera_monitor.py
```

흐름:

```text
PIR 24시간 감시
  -> 움직임 감지
  -> pir_motion_detected 로그
  -> 스냅샷 저장
  -> snapshot_saved 로그
  -> 선택적으로 5초 영상 저장
```

이 단계의 완료 기준:

- 사람이 지나가면 콘솔에 PIR 로그가 찍힌다.
- 같은 시점의 스냅샷 파일이 `data/snapshots/`에 생성된다.
- 이벤트 로그에 스냅샷 경로가 남는다.

## 12. 5단계: 도난 판단 연결

PIR과 무게 감지를 통합한다.

### 12.1 상태

```text
IDLE
  택배 없음

GUARD_MODE
  택배 보관 중

MOTION_DETECTED
  보관 중 사람이 접근함

THEFT_CONFIRMED
  사용자 인증 없이 무게가 감소함
```

### 12.2 판단 조건

도난 확정 조건:

```text
GUARD_MODE 상태
PIR 움직임 감지
무게가 기준 이상 감소
사용자 인증 없음
  -> theft_confirmed
```

단순 통행 조건:

```text
GUARD_MODE 상태
PIR 움직임 감지
무게 변화 없음
  -> passerby_motion
```

무게만 줄어든 경우:

```text
GUARD_MODE 상태
PIR 미감지
무게 감소
  -> suspicious_weight_change
```

## 13. 6단계: 경보와 알림

도난 이벤트가 확정된 뒤 붙인다.

파일:

```text
src/smart_delivery_container/alerts/local_alarm.py
src/smart_delivery_container/alerts/mqtt_notifier.py
```

동작:

```text
theft_confirmed
  -> 사이렌 출력
  -> 스냅샷/영상 저장
  -> MQTT 또는 FCM 알림 전송
  -> theft_alert_sent 로그 저장
```

초기 구현에서는 MQTT를 먼저 사용한다. FCM은 스마트폰 앱 또는 Firebase 설정이 필요하므로 나중에 붙인다.

## 14. 전체 실행 스크립트

최종 실행 파일:

```text
scripts/run_system.py
```

최종 흐름:

```text
설정 로드
이벤트 로그 초기화
PIR 센서 초기화
카메라 초기화
무게 센서 초기화
경보/알림 초기화

while True:
  PIR 값 읽기
  무게 값 읽기
  상태 머신 업데이트
  이벤트 발생 시 로그 저장
  필요한 경우 카메라/경보/알림 실행
```

## 15. 테스트 순서

처음부터 만들 때는 반드시 아래 순서로 테스트한다.

1. 소프트웨어 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

2. PIR 시뮬레이션 테스트

```bash
PIR_SAMPLE_INTERVAL_MS=1 PIR_COOLDOWN_MS=0 \
python3 scripts/check_pir.py --simulate 0,0,1,1,0,1 --max-ticks 6
```

3. 실제 PIR 테스트

```bash
python3 scripts/check_pir.py
```

4. 카메라 테스트

```bash
python3 scripts/check_camera.py
```

5. 무게 감지 시뮬레이션 테스트

```bash
SAMPLE_INTERVAL_MS=1 MOVING_AVERAGE_SIZE=1 STABLE_DURATION_MS=3 \
python3 scripts/run_weight_monitor.py \
  --simulate 0,0,0,500,500,500,500,500,0,0,0,0,0 \
  --max-ticks 13
```

6. 실제 로드셀 보정

```bash
python3 scripts/calibrate_weight.py
```

7. 전체 시스템 테스트

```bash
python3 scripts/run_system.py
```

## 16. 완료 기준

### 16.1 PIR 1차 완료

- PIR 움직임 감지 시 콘솔에 로그가 찍힌다.
- `data/events/events.jsonl`에 `pir_motion_detected` 이벤트가 저장된다.
- PIR 신호가 계속 True여도 같은 움직임에 대해 로그가 반복 폭주하지 않는다.

### 16.2 카메라 1차 완료

- PIR 감지 시 스냅샷이 저장된다.
- 저장된 파일 경로가 이벤트 로그에 남는다.

### 16.3 무게 감지 1차 완료

- 택배를 올리면 `package_detected`가 발생한다.
- 택배를 제거하면 `package_removed`가 발생한다.
- 짧은 진동이나 노이즈로는 제거 이벤트가 발생하지 않는다.

### 16.4 통합 완료

- 보관 중 사람이 접근하면 카메라가 켜진다.
- 보관 중 무게가 줄면 도난 후보로 판단한다.
- PIR 접근과 무게 감소가 함께 확인되면 도난 이벤트가 확정된다.
- 도난 이벤트 시 영상, 경보, 알림, 로그가 모두 실행된다.
