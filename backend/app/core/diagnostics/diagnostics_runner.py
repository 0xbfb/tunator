from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config.tor_config_manager import TorConfigManager
from app.core.detection.environment_detector import EnvironmentDetectionResult, EnvironmentDetector
from app.core.service.tor_service_manager import TorServiceManager


@dataclass(slots=True)
class DiagnosticCheck:
    name: str
    ok: bool
    details: str


@dataclass(slots=True)
class DiagnosticRunResult:
    run_id: str | None
    checked_at: str
    source: str
    freshness: str
    checks: list[DiagnosticCheck]


class DiagnosticsRunner:
    def __init__(self, env: EnvironmentDetectionResult, detector: EnvironmentDetector, service_manager: TorServiceManager, config_manager: TorConfigManager):
        self.env = env
        self.detector = detector
        self.service_manager = service_manager
        self.config_manager = config_manager

    def run(self, source: str = "manual", expected_run_id: str | None = None, retries: int = 0, backoff_seconds: float = 0.4) -> DiagnosticRunResult:
        checks: list[DiagnosticCheck] = []
        for attempt in range(retries + 1):
            checks = self._collect_checks()
            service_check = next((item for item in checks if item.name == "service_running"), None)
            if service_check and service_check.ok:
                break
            if attempt < retries:
                time.sleep(backoff_seconds * (attempt + 1))

        status = self.service_manager.status()
        run_id = status.run_id
        freshness = "fresh" if expected_run_id is None or expected_run_id == run_id else "stale"
        return DiagnosticRunResult(
            run_id=run_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
            source=source,
            freshness=freshness,
            checks=checks,
        )

    def _collect_checks(self) -> list[DiagnosticCheck]:
        config = self.config_manager.read_parsed()
        socks_port = int(config.get("SOCKSPort", "9050")) if config.get("SOCKSPort", "9050").isdigit() else 9050
        control_port = int(config.get("ControlPort", "9051")) if config.get("ControlPort", "9051").isdigit() else 9051
        status = self.service_manager.status()

        checks = [
            DiagnosticCheck(name="tor_binary_detected", ok=self.env.tor_installed, details=self.env.tor_binary_path or "Project-local Tor binary not found"),
            DiagnosticCheck(name="torrc_detected", ok=bool(self.env.torrc_path), details=self.env.torrc_path or "Project-local torrc not found"),
            DiagnosticCheck(name="runtime_platform_supported", ok=self.env.supported_platform, details=self.env.bundle_download_url or "No official bundle mapped for this platform"),
            DiagnosticCheck(name="service_running", ok=status.running, details=status.message),
            DiagnosticCheck(name="socks_port_open", ok=self.detector.is_port_open("127.0.0.1", socks_port), details=f"Checked 127.0.0.1:{socks_port}"),
            DiagnosticCheck(name="control_port_open", ok=self.detector.is_port_open("127.0.0.1", control_port), details=f"Checked 127.0.0.1:{control_port}"),
        ]
        return checks
