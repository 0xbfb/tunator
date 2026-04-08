from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class LogEntry:
    raw: str
    observed_at: str


class LogReader:
    def __init__(self, log_path: str | None):
        self.log_path = log_path

    def read_recent(self, limit: int = 200) -> list[LogEntry]:
        if not self.log_path:
            return []

        path = Path(self.log_path)
        if not path.exists():
            return []

        lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        tail = lines[-max(1, limit):]
        observed_at = datetime.now(timezone.utc).isoformat()
        return [LogEntry(raw=line, observed_at=observed_at) for line in tail]
