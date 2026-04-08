from pydantic import BaseModel


class LogEntry(BaseModel):
    raw: str
    observed_at: str


class LogResponse(BaseModel):
    entries: list[LogEntry]
