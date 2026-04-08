from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ServiceStatusResponse(BaseModel):
    running: bool
    source: str
    message: str
    pid: int | None = None


class ServiceActionResponse(BaseModel):
    success: bool
    action: str
    message: str
    pid: int | None = None
