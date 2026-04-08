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
    managed_by_tunator: bool = False
    control_connected: bool = False
    control_authenticated: bool = False
    tor_version: str | None = None
    bootstrap_phase: str | None = None
    bootstrap_progress: int | None = None
    control_auth_error: str | None = None
    latest_diagnostics: dict | None = None


class ServiceActionResponse(BaseModel):
    success: bool
    action: str
    message: str
    pid: int | None = None
    run_id: str | None = None
    status: str | None = None
    phase: str | None = None
