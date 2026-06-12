import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

_EVENT_FILE = Path(os.getenv("EVENT_OUTPUT_DIR", "data/events")) / "events.jsonl"


def _ensure_dir() -> None:
    _EVENT_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_event(event_type: str, payload: dict | object | None = None) -> dict:
    data: dict = {}
    if payload is not None:
        data = asdict(payload) if is_dataclass(payload) else dict(payload)  # type: ignore[arg-type]
    data["event_type"] = event_type
    data["created_at"] = datetime.now(timezone.utc).isoformat()

    _ensure_dir()
    with _EVENT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")

    print(f"[EVENT] {data}")
    return data
