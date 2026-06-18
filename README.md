# Smart Delivery Container

택배함 무게 감지 + 카메라 + 텔레그램 알림 시스템  
(Raspberry Pi + HX711 로드셀 + HC-SR04 초음파 + CSI 카메라 + 패시브 버저)

---

## 하드웨어 핀 연결

| 부품 | 신호 | BCM | 물리 핀 |
|---|---|---|---|
| HX711 로드셀 | DT (DATA) | GPIO 5 | 핀 29 |
| HX711 로드셀 | SCK (CLK) | GPIO 6 | 핀 31 |
| HC-SR04 초음파 | TRIG | GPIO 23 | 핀 16 |
| HC-SR04 초음파 | ECHO | GPIO 24 | 핀 18 |
| 패시브 버저 | IN | GPIO 18 | 핀 12 |
| 카메라 | CSI 커넥터 | — | CSI |

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
서버: http://192.168.x.x:5000
```

### 3. 웹 UI 접속

같은 와이파이에 연결된 PC나 스마트폰 브라우저에서 위 주소로 접속합니다.  
라즈베리파이 자체에서는 `http://localhost:5000`

---

## 동작 흐름

1. **물건 놓기** → HX711이 무게 증가 감지, 카메라 버퍼링 시작
2. **물건 꺼내기** → 무게가 임계값(기본 500g) 아래로 떨어지면
   - 버저 경보음 (GPIO18, 1800Hz ↔ 1000Hz 교차 3회)
   - 텔레그램 텍스트 알림 전송
   - 이전 최대 30초 + 이후 10초 영상을 MP4로 저장 후 텔레그램 전송

---

## 주요 설정값 (`smart_delivery_container/webapp/app.py`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `WEIGHT_THRESHOLD` | 500 g | 이벤트 트리거 무게 |
| `WEIGHT_AVG_WINDOW_S` | 5 초 | 이동 평균 윈도우 |
| `WEIGHT_CANDIDATE_WINDOW_S` | 5 초 | 스파이크 확인 대기 |
| `PRE_EVENT_BUFFER_SECONDS` | 30 초 | 이전 영상 버퍼 |
| `POST_EVENT_SECONDS` | 10 초 | 이후 영상 추가 녹화 |
| `EVENT_COOLDOWN_SECONDS` | 10 초 | 연속 이벤트 방지 |
| `AUTO_TARE_STABLE_S` | 20 초 | 자동 영점 조정 대기 |

---

## 프로젝트 구조

```
Projects3/
├── smart_delivery_container/   # 웹 서버 (메인 실행 파일)
│   └── webapp/
│       ├── app.py              # Flask 서버 (여기를 실행)
│       └── templates/
│           └── index.html
├── smartDeliveryContainer/     # 센서/알람 Python 라이브러리
│   ├── config/.env             # 환경변수 (텔레그램 토큰 등)
│   ├── scripts/
│   │   ├── calibrate_weight.py # 로드셀 캘리브레이션
│   │   └── run_weight_monitor.py
│   └── src/smart_delivery_container/
│       ├── alerts/             # speaker_alarm, telegram_notifier
│       ├── camera/             # camera_recorder
│       ├── sensors/            # hcsr04, weight
│       └── core/               # config, weight_monitor
└── myenv/                      # Python 가상환경
```
