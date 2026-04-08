from pydantic import BaseModel, Field

from app.schemas.onion import OnionServiceItem


class ConfigValidationRequest(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)


class ConfigApplyRequest(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)


class ConfigValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class ConfigReadResponse(BaseModel):
    raw: str
    parsed: dict[str, str]
    base_options: dict[str, str]
    onion_services: list[OnionServiceItem]
    supported_options: list[str]
