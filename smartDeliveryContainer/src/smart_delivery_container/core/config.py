import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parents[3] / "config" / ".env", override=False)
load_dotenv(override=False)


@dataclass
class PirConfig:
    pin: int = field(default_factory=lambda: int(os.getenv("PIR_PIN", "17")))
    sample_interval_ms: int = field(default_factory=lambda: int(os.getenv("PIR_SAMPLE_INTERVAL_MS", "100")))
    cooldown_ms: int = field(default_factory=lambda: int(os.getenv("PIR_COOLDOWN_MS", "2000")))


@dataclass
class WeightConfig:
    hx711_dout_pin: int = field(default_factory=lambda: int(os.getenv("HX711_DOUT_PIN", "5")))
    hx711_sck_pin: int = field(default_factory=lambda: int(os.getenv("HX711_SCK_PIN", "6")))
    sample_interval_ms: int = field(default_factory=lambda: int(os.getenv("SAMPLE_INTERVAL_MS", "100")))
    moving_average_size: int = field(default_factory=lambda: int(os.getenv("MOVING_AVERAGE_SIZE", "10")))
    package_detect_threshold_g: float = field(default_factory=lambda: float(os.getenv("PACKAGE_DETECT_THRESHOLD_G", "300")))
    package_remove_threshold_ratio: float = field(default_factory=lambda: float(os.getenv("PACKAGE_REMOVE_THRESHOLD_RATIO", "0.6")))
    stable_duration_ms: int = field(default_factory=lambda: int(os.getenv("STABLE_DURATION_MS", "1500")))
    drift_tolerance_g: float = field(default_factory=lambda: float(os.getenv("DRIFT_TOLERANCE_G", "50")))
    calibration_offset: float = field(default_factory=lambda: float(os.getenv("CALIBRATION_OFFSET", "0")))
    calibration_scale: float = field(default_factory=lambda: float(os.getenv("CALIBRATION_SCALE", "1")))


@dataclass
class CameraConfig:
    index: int = field(default_factory=lambda: int(os.getenv("CAMERA_INDEX", "0")))
    video_output_dir: Path = field(default_factory=lambda: Path(os.getenv("VIDEO_OUTPUT_DIR", "data/videos")))
    snapshot_output_dir: Path = field(default_factory=lambda: Path(os.getenv("SNAPSHOT_OUTPUT_DIR", "data/snapshots")))
    event_output_dir: Path = field(default_factory=lambda: Path(os.getenv("EVENT_OUTPUT_DIR", "data/events")))


@dataclass
class HcSr04Config:
    trigger_pin: int = field(default_factory=lambda: int(os.getenv("HCSR04_TRIGGER_PIN", "23")))
    echo_pin: int = field(default_factory=lambda: int(os.getenv("HCSR04_ECHO_PIN", "24")))
    threshold_cm: float = field(default_factory=lambda: float(os.getenv("HCSR04_THRESHOLD_CM", "20.0")))
    sample_interval_ms: int = field(default_factory=lambda: int(os.getenv("HCSR04_SAMPLE_INTERVAL_MS", "100")))
    cooldown_ms: int = field(default_factory=lambda: int(os.getenv("HCSR04_COOLDOWN_MS", "2000")))


@dataclass
class SpeakerConfig:
    pin: int = field(default_factory=lambda: int(os.getenv("SPEAKER_PIN", "18")))
    frequency: int = field(default_factory=lambda: int(os.getenv("SPEAKER_FREQUENCY", "2000")))


@dataclass
class TelegramConfig:
    token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))


@dataclass
class MqttConfig:
    host: str = field(default_factory=lambda: os.getenv("MQTT_HOST", ""))
    port: int = field(default_factory=lambda: int(os.getenv("MQTT_PORT", "1883")))
    topic: str = field(default_factory=lambda: os.getenv("MQTT_TOPIC", "smart-delivery/events"))


@dataclass
class RuntimeConfig:
    pir: PirConfig = field(default_factory=PirConfig)
    hcsr04: HcSr04Config = field(default_factory=HcSr04Config)
    weight: WeightConfig = field(default_factory=WeightConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
