from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from app.core.detection.environment_detector import EnvironmentDetectionResult


@dataclass(slots=True)
class ServiceActionResult:
    success: bool
    action: str
    message: str
    pid: int | None = None


@dataclass(slots=True)
class ServiceStatusResult:
    running: bool
    source: str
    message: str
    pid: int | None = None


class TorServiceManager:
    _process: ClassVar[subprocess.Popen[str] | None] = None

    def __init__(self, env: EnvironmentDetectionResult):
        self.env = env

    def status(self) -> ServiceStatusResult:
        process = self.__class__._process
        if process and process.poll() is None:
            return ServiceStatusResult(
                running=True,
                source="managed-process",
                message="Project-local Tor process is running.",
                pid=process.pid,
            )
        return ServiceStatusResult(
            running=False,
            source="managed-process",
            message="Project-local Tor process is not running.",
        )

    def start(self) -> ServiceActionResult:
        current = self.status()
        if current.running:
            return ServiceActionResult(success=True, action="start", message="Tor is already running.", pid=current.pid)

        if not self.env.tor_binary_path:
            return ServiceActionResult(
                success=False,
                action="start",
                message="Project-local Tor binary was not found. Run the bootstrap script first.",
            )
        if not self.env.torrc_path:
            return ServiceActionResult(success=False, action="start", message="Project-local torrc was not found.")

        tor_binary = Path(self.env.tor_binary_path)
        tor_cwd = str(tor_binary.parent)

        verify = subprocess.run(
            [self.env.tor_binary_path, "--verify-config", "-f", self.env.torrc_path],
            capture_output=True,
            text=True,
            check=False,
            cwd=tor_cwd,
        )
        if verify.returncode != 0:
            output = (verify.stderr or verify.stdout or "Tor configuration validation failed.").strip()
            return ServiceActionResult(success=False, action="start", message=output)

        try:
            self.__class__._process = subprocess.Popen(
                [self.env.tor_binary_path, "-f", self.env.torrc_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=tor_cwd,
            )
            process = self.__class__._process
            time.sleep(1.5)
            if process and process.poll() is not None:
                self.__class__._process = None
                return ServiceActionResult(
                    success=False,
                    action="start",
                    message=self._build_early_exit_message(),
                )
            return ServiceActionResult(
                success=True,
                action="start",
                message="Project-local Tor started successfully.",
                pid=process.pid if process else None,
            )
        except OSError as exc:
            return ServiceActionResult(success=False, action="start", message=f"Failed to start project-local Tor: {exc}")

    def stop(self) -> ServiceActionResult:
        process = self.__class__._process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            self.__class__._process = None
            return ServiceActionResult(success=True, action="stop", message="Project-local Tor stopped.")

        self.__class__._process = None
        return ServiceActionResult(success=False, action="stop", message="No project-local Tor process is being managed.")

    def restart(self) -> ServiceActionResult:
        stop_result = self.stop()
        if not stop_result.success and "No project-local Tor process" not in stop_result.message:
            return ServiceActionResult(success=False, action="restart", message=stop_result.message)
        return self.start()

    def _build_early_exit_message(self) -> str:
        log_path = Path(self.env.log_path) if self.env.log_path else None
        if log_path and log_path.exists():
            lines = [line.strip() for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
            if lines:
                tail = " | ".join(lines[-6:])
                return f"Project-local Tor exited right after start. Recent log lines: {tail}"
        return "Project-local Tor exited right after start. Check the logs and torrc values."
