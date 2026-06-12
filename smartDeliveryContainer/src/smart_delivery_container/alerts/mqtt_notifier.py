from __future__ import annotations
import json
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt  # type: ignore[import]
    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False


class MqttNotifier:
    def __init__(self, host: str, port: int = 1883, topic: str = "smart-delivery/events") -> None:
        self._host = host
        self._port = port
        self._topic = topic
        self._client = None
        if _MQTT_AVAILABLE and host:
            self._client = mqtt.Client()
            self._client.connect(host, port, keepalive=60)
            self._client.loop_start()

    def send(self, event_type: str, payload: dict | None = None) -> None:
        data = {"event_type": event_type, "created_at": datetime.now(timezone.utc).isoformat()}
        if payload:
            data.update(payload)
        msg = json.dumps(data, ensure_ascii=False)
        if self._client:
            self._client.publish(self._topic, msg)
        else:
            print(f"[MQTT] {msg}")

    def close(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
