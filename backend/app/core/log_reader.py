from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class LogEntry:
    raw: str
    observed_at: str
    timestamp: str | None = None
    level: str | None = None
    source: str = "tor"
    message: str | None = None


class LogReader:
    def __init__(self, log_path: str | None):
        self.log_path = log_path

    def read_recent(self, limit: int = 200) -> list[LogEntry]:
        if not self.log_path:
            return []
        path = Path(self.log_path)
        if not path.exists() or path.stat().st_size == 0:
            return []

        tail = self._tail_lines(path, max(1, limit))
        observed_at = datetime.now(timezone.utc).isoformat()
        return [self._parse_line(line, observed_at) for line in tail if line.strip()]

    def _tail_lines(self, path: Path, limit: int) -> list[str]:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            buffer = bytearray()
            lines: list[bytes] = []
            pos = handle.tell()
            while pos > 0 and len(lines) <= limit:
                chunk_size = min(4096, pos)
                pos -= chunk_size
                handle.seek(pos)
                chunk = handle.read(chunk_size)
                buffer[:0] = chunk
                lines = buffer.splitlines()
            selected = lines[-limit:]
            return [line.decode("utf-8", errors="ignore") for line in selected]

    def _parse_line(self, line: str, observed_at: str) -> LogEntry:
        stripped = line.strip()
        level = None
        message = stripped
        timestamp = None
        match = re.match(r"^\[([^\]]+)\]\s*(.*)$", stripped)
        if match:
            level = match.group(1).lower()
            message = match.group(2)
        ts_match = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s+(.*)$", message)
        if ts_match:
            timestamp = ts_match.group(1)
            message = ts_match.group(2)
        return LogEntry(raw=stripped, observed_at=observed_at, timestamp=timestamp, level=level, message=message)
