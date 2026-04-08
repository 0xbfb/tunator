from pydantic import BaseModel


class LogEntry(BaseModel):
    raw: str
    observed_at: str
    timestamp: str | None = None
    level: str | None = None
    source: str = "tor"
    message: str | None = None


class LogResponse(BaseModel):
    entries: list[LogEntry]
