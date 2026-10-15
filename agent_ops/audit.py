"""Append-only JSONL audit log. Every model call, tool call and approval decision lands here."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from . import config


class AuditLog:
    def __init__(self, path: Path | None = None, run_id: str | None = None, persist: bool = True):
        self.path = Path(path or config.RUNS_DIR / "audit.jsonl")
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.persist = persist
        self.events: list[dict[str, Any]] = []
        if persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **payload: Any) -> None:
        record = {"ts": round(time.time(), 3), "run_id": self.run_id, "event": event, **payload}
        self.events.append(record)
        if self.persist:
            with self.path.open("a") as fh:
                fh.write(json.dumps(record, default=str) + "\n")

    def of_type(self, event: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["event"] == event]
