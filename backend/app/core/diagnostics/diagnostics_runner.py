from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config.tor_config_manager import TorConfigManager
from app.core.detection.environment_detector import EnvironmentDetectionResult, EnvironmentDetector
from app.core.service.tor_service_manager import TorServiceManager


@dataclass(slots=True)
class DiagnosticCheck:
    name: str
    ok: bool
    details: str
    recommendation: str | None = None


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
        return DiagnosticRunResult(run_id=run_id, checked_at=datetime.now(timezone.utc).isoformat(), source=source, freshness=freshness, checks=checks)

    def _collect_checks(self) -> list[DiagnosticCheck]:
        config = self.config_manager.read_parsed()
        socks_port = int(config.get("SOCKSPort", "9050")) if config.get("SOCKSPort", "9050").isdigit() else 9050
        control_port = int(config.get("ControlPort", "9051")) if config.get("ControlPort", "9051").isdigit() else 9051
        status = self.service_manager.status()
        onions = self.config_manager.list_onion_services()

        checks = [
            DiagnosticCheck("tor_binary_detected", self.env.tor_installed, self.env.tor_binary_path or "Project-local Tor binary not found", "Execute bootstrap script to install bundled runtime."),
            DiagnosticCheck("torrc_detected", bool(self.env.torrc_path), self.env.torrc_path or "Project-local torrc not found", "Regenerate torrc with bootstrap-local-tor."),
            DiagnosticCheck("runtime_platform_supported", self.env.supported_platform, self.env.bundle_download_url or "No official bundle mapped for this platform", "Use explicit TUNATOR_TOR_BINARY if your platform is not mapped."),
            DiagnosticCheck("service_running", status.running, status.message, "Check startup logs and run start/restart if needed."),
            DiagnosticCheck("socks_port_open", self.detector.is_port_open("127.0.0.1", socks_port), f"Checked 127.0.0.1:{socks_port}", "Port may be occupied or Tor failed bootstrap."),
            DiagnosticCheck("control_port_open", self.detector.is_port_open("127.0.0.1", control_port), f"Checked 127.0.0.1:{control_port}", "Enable ControlPort and CookieAuthentication for richer diagnostics."),
            DiagnosticCheck("control_port_authenticated", status.control_authenticated, status.control_auth_error or "ControlPort authentication ok" if status.control_connected else "ControlPort unavailable", "Check DataDirectory/control_auth_cookie permissions."),
            DiagnosticCheck("bootstrap_reasonable", (status.bootstrap_progress or 0) >= 50 if status.bootstrap_progress is not None else status.running, status.bootstrap_phase or "No bootstrap data", "Wait bootstrap or inspect reachability/firewall."),
            DiagnosticCheck("log_file_present", bool(self.env.log_path and Path(self.env.log_path).exists()), self.env.log_path or "No log path", "Set Log notice file in torrc for troubleshooting."),
        ]

        if onions:
            missing = [item["name"] for item in onions if not item.get("hostname_ready")]
            checks.append(
                DiagnosticCheck(
                    "onion_hostnames_generated",
                    not missing,
                    "Pending hostnames: " + ", ".join(missing) if missing else "All onion hostnames are present",
                    "Restart Tor and validate local target reachability if hostnames stay pending.",
                )
            )
        return checks
