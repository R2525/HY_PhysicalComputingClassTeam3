# 프로젝트 구조 보고

## 생성일
2026-05-29

## 디렉터리 구조

```
smartDeliveryContainer/
  config/
    settings.example.env        # 환경변수 예시 (복사 후 .env로 사용)
  data/
    events/                     # 이벤트 JSONL 로그
    snapshots/                  # 카메라 스냅샷
    videos/                     # 이벤트 영상
  doc/
    implements/                 # 구현 보고서 (이 폴더)
  logs/                         # 실행 로그
  scripts/
    check_pir.py                # 1단계: PIR 단독 테스트
    check_camera.py             # 2단계: 카메라 테스트
    calibrate_weight.py         # 로드셀 보정
    run_weight_monitor.py       # 3단계: 무게 감지 테스트
    run_pir_camera_monitor.py   # 4단계: PIR+카메라 연동
    run_system.py               # 5단계: 전체 시스템 실행
  src/
    smart_delivery_container/
      alerts/
        local_alarm.py          # DFPlayer Mini 경보음
        mqtt_notifier.py        # MQTT 스마트폰 알림
      camera/
        camera_recorder.py      # OpenCV 스냅샷/녹화
      core/
        config.py               # 환경변수 → 설정 객체
        package_detector.py     # 택배 적재/제거 상태 머신
        pir_camera_monitor.py   # PIR+카메라 연동
        pir_monitor.py          # PIR 감지 루프
        weight_monitor.py       # 무게 감지 루프
      sensors/
        pir_sensor.py           # PIR 인터페이스 (GPIO / 시뮬레이션)
        weight_sensor.py        # HX711 인터페이스 (GPIO / 시뮬레이션)
        weight_filter.py        # 이동평균 필터
      utils/
        event_log.py            # JSONL 이벤트 저장
  tests/
    test_pir_monitor.py
    test_camera_paths.py
    test_weight_filter.py
    test_package_detector.py
  requirements.txt
  requirements-raspi.txt
  pyproject.toml
  .gitignore
```

## 구현 완료 목록

| 단계 | 파일 | 상태 |
|------|------|------|
| 공통 설정 | core/config.py | 완료 |
| 이벤트 로그 | utils/event_log.py | 완료 |
| PIR 감지 | sensors/pir_sensor.py, core/pir_monitor.py | 완료 |
| 카메라 | camera/camera_recorder.py | 완료 |
| 무게 필터 | sensors/weight_filter.py | 완료 |
| 무게 센서 | sensors/weight_sensor.py | 완료 |
| 택배 감지 상태 머신 | core/package_detector.py | 완료 |
| 무게 모니터 | core/weight_monitor.py | 완료 |
| PIR+카메라 연동 | core/pir_camera_monitor.py | 완료 |
| 경보음 | alerts/local_alarm.py | 완료 |
| MQTT 알림 | alerts/mqtt_notifier.py | 완료 |
| 전체 시스템 | scripts/run_system.py | 완료 |

## 테스트 실행

```bash
cd smartDeliveryContainer
python3 -m venv .venv && source .venv/bin/activate
pip install pytest python-dotenv
PYTHONPATH=src python3 -m pytest tests/ -v
```
