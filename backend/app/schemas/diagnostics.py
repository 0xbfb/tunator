from pydantic import BaseModel


class DiagnosticItem(BaseModel):
    name: str
    ok: bool
    details: str


class DiagnosticsResponse(BaseModel):
    checks: list[DiagnosticItem]
