from pydantic import BaseModel


class EnvironmentInfo(BaseModel):
    os_name: str
    tor_binary_path: str | None
    torrc_path: str | None
    log_path: str | None
    service_name: str | None
    tor_installed: bool
    service_available: bool
    tor_source: str
    vendor_root: str
    supported_platform: bool
    bundle_archive_path: str | None
    bundle_download_url: str | None
