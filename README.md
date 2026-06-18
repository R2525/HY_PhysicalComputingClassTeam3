# Smart Delivery Container

택배함 무게 감지 + 카메라 + 텔레그램 알림 시스템  
Raspberry Pi + HX711 로드셀 + HC-SR04 초음파 + CSI 카메라 + 패시브 버저

---

## 하드웨어 핀 연결

| 부품 | 신호 | BCM | 물리 핀 |
|---|---|---|---|
| HX711 로드셀 | DT (DATA) | GPIO 5 | 핀 29 |
| HX711 로드셀 | SCK (CLK) | GPIO 6 | 핀 31 |
| HC-SR04 초음파 | TRIG | GPIO 23 | 핀 16 |
| HC-SR04 초음파 | ECHO | GPIO 24 | 핀 18 |
| 패시브 버저 | IN | GPIO 18 | 핀 12 (하드웨어 PWM) |
| 카메라 | — | CSI 커넥터 | CSI |

---

## 환경 설정

`smartDeliveryContainer/config/.env` 파일에 텔레그램 정보를 입력합니다.

```env
TELEGRAM_TOKEN=<봇 토큰>
TELEGRAM_CHAT_ID=<채팅 ID>
```

---

## 실행 방법

### 1. 가상환경 활성화

```bash
cd /home/phc_13/Projects3
source myenv/bin/activate
```

### 2. 웹 서버 실행

```bash
cd smart_delivery_container/webapp
python3 app.py
```

터미널에 아래와 같이 출력됩니다:
```
[SPEAKER] 초기화 완료 — GPIO18, 2000Hz
서버: http://192.168.x.x:5000
```

### 3. 웹 UI 접속

같은 와이파이에 연결된 PC나 스마트폰 브라우저에서 위 주소로 접속합니다.  
라즈베리파이 자체에서는 `http://localhost:5000`

---

## 동작 흐름

1. **물건 놓기** → HX711이 무게 증가 감지, 카메라 버퍼링 시작
2. **물건 꺼내기** → 무게가 임계값 아래로 떨어지면 (5초 이동 평균 기준)
   - 버저 경보음 (GPIO18 — 1800Hz ↔ 1000Hz 교차 3회)
   - 텔레그램 텍스트 알림 전송
   - 이전 N초 + 이후 10초 영상을 MP4로 저장 후 텔레그램 전송

### 텔레그램 기본 메시지 형식

```
SmartDeliveryContainer 알림
시각: 2026-06-18 12:00:00
5초 평균: 320.5g
원본: 318.2g
초음파: 45.2cm
영상: 이전 저장분 30.0초 + 이후 10초
```

웹 UI에서 추가 메시지를 입력하면 맨 위에 붙습니다.

---

## 웹 UI 기능

| 기능 | 설명 |
|---|---|
| 라이브 스트림 | CSI 카메라 실시간 영상 |
| 무게 게이지 | 5초 평균 / 원본 / 후보값 실시간 표시 |
| 임계값 슬라이더 | 이벤트 트리거 기준 무게 (g) 조정 |
| 영점 (Tare) | 현재 무게를 0으로 초기화 |
| 초음파 로그 | HC-SR04 감지 이력 |
| 알림 설정 | 이전 영상 길이 (1~60초) + 텔레그램 추가 메시지 설정 |
| 자동 캡처 이력 | 이벤트 발생 시 저장된 영상 목록 |

---

## 주요 설정값 (`smart_delivery_container/webapp/app.py`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `WEIGHT_THRESHOLD` | 500 g | 이벤트 트리거 무게 (웹 UI에서도 변경 가능) |
| `WEIGHT_AVG_WINDOW_S` | 5 초 | 이동 평균 윈도우 |
| `WEIGHT_CANDIDATE_WINDOW_S` | 5 초 | 스파이크 확인 대기 |
| `PRE_EVENT_BUFFER_SECONDS` | 30 초 | 이전 영상 버퍼 기본값 (웹 UI에서 변경 가능) |
| `POST_EVENT_SECONDS` | 10 초 | 이후 영상 추가 녹화 |
| `EVENT_COOLDOWN_SECONDS` | 10 초 | 연속 이벤트 방지 |
| `AUTO_TARE_STABLE_S` | 20 초 | 자동 영점 조정 대기 |
| `SPEAKER_PIN` | 18 | 버저 BCM 핀 번호 |
| `SPEAKER_FREQUENCY` | 2000 Hz | 버저 기본 주파수 |

---

## 프로젝트 구조

```
Projects3/
├── smart_delivery_container/   # 웹 서버 (메인 실행 파일)
│   └── webapp/
│       ├── app.py              # Flask 서버 — 여기를 실행
│       └── templates/
│           └── index.html      # 웹 UI
├── smartDeliveryContainer/     # 센서/알람 Python 라이브러리
│   ├── config/.env             # 환경변수 (텔레그램 토큰 등, git 제외)
│   ├── scripts/
│   │   ├── calibrate_weight.py # 로드셀 캘리브레이션
│   │   ├── check_camera.py     # 카메라 동작 확인
│   │   ├── run_weight_monitor.py
│   │   └── run_system.py
│   └── src/smart_delivery_container/
│       ├── alerts/             # speaker_alarm, telegram_notifier
│       ├── camera/             # camera_recorder
│       ├── sensors/            # hcsr04, weight
│       └── core/               # config, weight_monitor
└── myenv/                      # Python 가상환경 (git 제외)
```
