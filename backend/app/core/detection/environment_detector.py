from __future__ import annotations

import os
import platform
import socket
from dataclasses import dataclass
from pathlib import Path

from app.core.vendor.tor_runtime_manager import TorRuntimeManager


@dataclass(slots=True)
class EnvironmentDetectionResult:
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


class EnvironmentDetector:
    def __init__(self, tor_binary_env: str | None = None, torrc_env: str | None = None, log_env: str | None = None):
        self._tor_binary_env = tor_binary_env or os.getenv("TUNATOR_TOR_BINARY")
        self._torrc_env = torrc_env or os.getenv("TUNATOR_TORRC_PATH")
        self._log_env = log_env or os.getenv("TUNATOR_LOG_PATH")
        self.runtime_manager = TorRuntimeManager()

    def detect(self) -> EnvironmentDetectionResult:
        os_name = platform.system().lower()
        self.runtime_manager.ensure_default_torrc()
        bundle_status = self.runtime_manager.bundle_status()

        tor_binary, tor_source = self._detect_tor_binary()
        torrc_path = self._detect_torrc_path()
        log_path = self._detect_log_path()

        return EnvironmentDetectionResult(
            os_name=os_name,
            tor_binary_path=tor_binary,
            torrc_path=torrc_path,
            log_path=log_path,
            service_name=None,
            tor_installed=tor_binary is not None,
            service_available=False,
            tor_source=tor_source,
            vendor_root=str(self.runtime_manager.runtime_platform_dir()),
            supported_platform=bool(bundle_status["supported"]),
            bundle_archive_path=bundle_status["archive_path"],
            bundle_download_url=bundle_status["bundle_url"],
        )

    def is_port_open(self, host: str, port: int, timeout: float = 0.5) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0

    def _detect_tor_binary(self) -> tuple[str | None, str]:
        if self._tor_binary_env:
            path = Path(self._tor_binary_env)
            if path.exists():
                return str(path), "explicit-env"

        runtime_binary = self.runtime_manager.runtime_binary_path()
        if runtime_binary and runtime_binary.exists():
            return str(runtime_binary), "project-bundled"

        return None, "missing"

    def _detect_torrc_path(self) -> str:
        if self._torrc_env and Path(self._torrc_env).exists():
            return self._torrc_env
        return str(self.runtime_manager.ensure_default_torrc())

    def _detect_log_path(self) -> str:
        if self._log_env and Path(self._log_env).exists():
            return self._log_env
        return str(self.runtime_manager.log_path())
