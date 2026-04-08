from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ServiceStatusResponse(BaseModel):
    running: bool
    source: str
    message: str
    pid: int | None = None
    run_id: str | None = None
    status: str
    phase: str
    started_at: str | None = None
    last_seen_at: str | None = None
    updated_at: str | None = None
    last_error: str | None = None
    socks_port: int | None = None
    control_port: int | None = None
    latest_diagnostics: dict | None = None


class ServiceActionResponse(BaseModel):
    success: bool
    action: str
    message: str
    pid: int | None = None
    run_id: str | None = None
    status: str | None = None
    phase: str | None = None
