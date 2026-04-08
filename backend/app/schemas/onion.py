from pydantic import BaseModel, Field


class OnionServiceCreateRequest(BaseModel):
    name: str
    public_port: int = Field(default=80, ge=1, le=65535)
    target_host: str = Field(default='127.0.0.1', min_length=1)
    target_port: int = Field(ge=1, le=65535)
    access_password: str | None = None


class OnionDeleteRequest(BaseModel):
    remove_directory: bool = False


class OnionServiceItem(BaseModel):
    name: str
    directory: str
    public_port: int
    target_host: str
    target_port: int
    hostname: str | None = None
    hostname_path: str | None = None
    hostname_ready: bool = False
    auth_enabled: bool = False
    auth_client_name: str | None = None


class OnionServiceListResponse(BaseModel):
    items: list[OnionServiceItem]


class OnionServiceCreateResponse(BaseModel):
    success: bool
    item: OnionServiceItem
    backup_path: str | None = None
    warnings: list[str] = Field(default_factory=list)


class OnionServiceDeleteResponse(BaseModel):
    success: bool
    name: str
    removed: bool
    backup_path: str | None = None
