from pydantic import BaseModel, Field

from app.schemas.onion import OnionServiceItem


class ConfigValidationRequest(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)
    advanced_mode: bool = False


class ConfigApplyRequest(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)
    advanced_mode: bool = False


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


class ConfigPreviewResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    diff: str


class BackupItem(BaseModel):
    name: str
    path: str
    size_bytes: int
    created_at: str


class BackupListResponse(BaseModel):
    items: list[BackupItem]


class BackupRestoreRequest(BaseModel):
    backup_name: str


class ConfigHistoryItem(BaseModel):
    id: int
    changed_fields: dict[str, str]
    applied_successfully: bool
    validation_errors: list[str]
    warnings: list[str]
    created_at: str


class ConfigHistoryResponse(BaseModel):
    items: list[ConfigHistoryItem]
