from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from banking_gpt.policy import redact


class EvidenceRecorder:
    def __init__(self, root: Path = Path("evidence"), run_id: str | None = None) -> None:
        self.run_id = run_id or f"run-{uuid4().hex[:12]}"
        self.directory = root / self.run_id
        self.screenshot_directory = self.directory / "screenshots"
        self.screenshot_directory.mkdir(parents=True, exist_ok=True)
        self.events_path = self.directory / "events.jsonl"
        self._sensitive_values: set[str] = set()

    def register_sensitive_values(self, values: Any) -> None:
        for value in values:
            if value is not None and str(value):
                self._sensitive_values.add(str(value))

    def _redact(self, value: Any) -> Any:
        redacted = _redact_data(value)
        if isinstance(redacted, str):
            for sensitive in self._sensitive_values:
                redacted = redacted.replace(sensitive, "[REDACTED]")
            return redacted
        if isinstance(redacted, dict):
            return {key: self._redact(item) for key, item in redacted.items()}
        if isinstance(redacted, list):
            return [self._redact(item) for item in redacted]
        return redacted

    def event(self, event_type: str, **data: Any) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "event": event_type,
            "data": self._redact(data),
        }
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, default=str) + "\n")

    def screenshot_path(self, label: str) -> Path:
        safe_label = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
        return self.screenshot_directory / f"{safe_label}.png"

    def trace_path(self) -> Path:
        return self.directory / "trace.zip"

    def save_result(self, result: Any) -> None:
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        (self.directory / "run.json").write_text(
            json.dumps(self._redact(payload), indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def _redact_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: _redact_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_data(item) for item in value]
    return value
