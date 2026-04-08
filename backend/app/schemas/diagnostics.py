from pydantic import BaseModel


class DiagnosticItem(BaseModel):
    name: str
    ok: bool
    details: str
    recommendation: str | None = None


class DiagnosticsResponse(BaseModel):
    run_id: str | None = None
    checked_at: str
    source: str
    freshness: str
    checks: list[DiagnosticItem]
