from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.detection.environment_detector import EnvironmentDetectionResult, EnvironmentDetector
from app.db.repository import DatabaseRepository


@dataclass(slots=True)
class ServiceActionResult:
    success: bool
    action: str
    message: str
    pid: int | None = None
    run_id: str | None = None
    status: str | None = None
    phase: str | None = None


@dataclass(slots=True)
class ServiceStatusResult:
    running: bool
    source: str
    message: str
    pid: int | None = None
    run_id: str | None = None
    status: str = "stopped"
    phase: str = "idle"
    started_at: str | None = None
    last_seen_at: str | None = None
    updated_at: str | None = None
    last_error: str | None = None
    socks_port: int | None = None
    control_port: int | None = None


class TorServiceManager:
    def __init__(self, env: EnvironmentDetectionResult, detector: EnvironmentDetector, repository: DatabaseRepository):
        self.env = env
        self.detector = detector
        self.repository = repository

    def status(self) -> ServiceStatusResult:
        runtime = self.repository.fetch_runtime()
        pid = runtime.get("pid")
        process_alive = self._pid_exists(pid)
        socks_port = runtime.get("socks_port") or 9050
        control_port = runtime.get("control_port") or 9051
        socks_open = self.detector.is_port_open("127.0.0.1", socks_port)
        control_open = self.detector.is_port_open("127.0.0.1", control_port)

        if not process_alive and runtime.get("status") in {"running", "starting", "restarting"}:
            self._persist_runtime(
                status="failed",
                phase="failed",
                last_error="Tor process not found for stored PID.",
                pid=None,
                last_seen_at=self._now_iso(),
            )
            runtime = self.repository.fetch_runtime()

        running = bool(process_alive and (socks_open or control_open or runtime.get("status") == "running"))
        if running and runtime.get("status") != "running":
            phase = "ready" if socks_open else "verifying_ports"
            self._persist_runtime(status="running", phase=phase, last_seen_at=self._now_iso(), last_error=None)
            runtime = self.repository.fetch_runtime()
        elif runtime.get("status") in {"starting", "restarting"} and process_alive:
            phase = "verifying_ports" if not socks_open else "bootstrap_in_progress"
            self._persist_runtime(phase=phase, last_seen_at=self._now_iso())
            runtime = self.repository.fetch_runtime()

        message = self._build_status_message(runtime, process_alive, socks_open, control_open)
        return ServiceStatusResult(
            running=running,
            source="runtime-db+os-probe",
            message=message,
            pid=runtime.get("pid"),
            run_id=runtime.get("run_id"),
            status=runtime.get("status") or "stopped",
            phase=runtime.get("phase") or "idle",
            started_at=runtime.get("started_at"),
            last_seen_at=runtime.get("last_seen_at"),
            updated_at=runtime.get("updated_at"),
            last_error=runtime.get("last_error"),
            socks_port=runtime.get("socks_port"),
            control_port=runtime.get("control_port"),
        )

    def start(self, socks_port: int, control_port: int) -> ServiceActionResult:
        current = self.status()
        if current.running:
            return ServiceActionResult(
                success=True,
                action="start",
                message="Tor já está em execução.",
                pid=current.pid,
                run_id=current.run_id,
                status=current.status,
                phase=current.phase,
            )

        if not self.env.tor_binary_path:
            return ServiceActionResult(success=False, action="start", message="Tor binary não encontrado.", status="failed", phase="failed")
        if not self.env.torrc_path:
            return ServiceActionResult(success=False, action="start", message="torrc não encontrado.", status="failed", phase="failed")

        run_id = str(uuid.uuid4())
        started_at = self._now_iso()
        self._persist_runtime(
            run_id=run_id,
            status="starting",
            phase="awaiting_initialization",
            pid=None,
            started_at=started_at,
            last_seen_at=started_at,
            last_error=None,
            socks_port=socks_port,
            control_port=control_port,
        )

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
            self._persist_runtime(status="failed", phase="failed", last_error=output)
            return ServiceActionResult(success=False, action="start", message=output, run_id=run_id, status="failed", phase="failed")

        try:
            process = subprocess.Popen(
                [self.env.tor_binary_path, "-f", self.env.torrc_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=tor_cwd,
            )
        except OSError as exc:
            message = f"Falha ao iniciar Tor: {exc}"
            self._persist_runtime(status="failed", phase="failed", last_error=message)
            return ServiceActionResult(success=False, action="start", message=message, run_id=run_id, status="failed", phase="failed")

        self._persist_runtime(pid=process.pid, phase="bootstrap_in_progress", last_seen_at=self._now_iso())
        return ServiceActionResult(
            success=True,
            action="start",
            message="Inicialização do Tor em andamento.",
            pid=process.pid,
            run_id=run_id,
            status="starting",
            phase="bootstrap_in_progress",
        )

    def stop(self) -> ServiceActionResult:
        runtime = self.repository.fetch_runtime()
        pid = runtime.get("pid")
        run_id = runtime.get("run_id")
        self._persist_runtime(status="stopping", phase="stopping", last_seen_at=self._now_iso())

        if pid and self._pid_exists(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                deadline = time.time() + 5
                while time.time() < deadline and self._pid_exists(pid):
                    time.sleep(0.2)
                if self._pid_exists(pid):
                    os.kill(pid, signal.SIGKILL)
            except OSError as exc:
                self._persist_runtime(status="failed", phase="failed", last_error=f"Erro ao parar processo: {exc}")
                return ServiceActionResult(success=False, action="stop", message=f"Erro ao parar processo: {exc}", run_id=run_id, status="failed", phase="failed")

        self._persist_runtime(status="stopped", phase="idle", pid=None, last_seen_at=self._now_iso(), last_error=None)
        return ServiceActionResult(success=True, action="stop", message="Tor parado.", run_id=run_id, status="stopped", phase="idle")

    def restart(self, socks_port: int, control_port: int) -> ServiceActionResult:
        self._persist_runtime(status="restarting", phase="stopping", last_seen_at=self._now_iso())
        stop_result = self.stop()
        if not stop_result.success:
            return ServiceActionResult(success=False, action="restart", message=stop_result.message, run_id=stop_result.run_id, status=stop_result.status, phase=stop_result.phase)
        start_result = self.start(socks_port=socks_port, control_port=control_port)
        start_result.action = "restart"
        return start_result

    def _pid_exists(self, pid: int | None) -> bool:
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _persist_runtime(self, **values: object) -> None:
        values["updated_at"] = self._now_iso()
        self.repository.update_runtime(values)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_status_message(self, runtime: dict[str, object], process_alive: bool, socks_open: bool, control_open: bool) -> str:
        status = runtime.get("status") or "stopped"
        phase = runtime.get("phase") or "idle"
        if status in {"starting", "restarting"}:
            if phase == "awaiting_initialization":
                return "Aguardando inicialização do processo Tor."
            if phase == "bootstrap_in_progress":
                return "Bootstrap em andamento."
            if phase == "verifying_ports":
                return "Processo ativo. Verificando portas."
        if status == "running":
            if socks_open or control_open:
                return "Tor pronto e respondendo portas configuradas."
            if process_alive:
                return "Processo Tor ativo; aguardando confirmação de portas."
        if status == "failed":
            err = runtime.get("last_error")
            return f"Falhou: {err}" if err else "Falha ao iniciar o Tor."
        if status == "stopping":
            return "Parando processo Tor."
        return "Tor parado."
