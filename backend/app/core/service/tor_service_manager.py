from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.core.constants import LOCAL_TOR_STATE_DIR
from app.core.detection.environment_detector import EnvironmentDetectionResult, EnvironmentDetector
from app.core.service.control_port_client import ControlPortInfo, query_control_port
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
    managed_by_tunator: bool = False
    control_connected: bool = False
    control_authenticated: bool = False
    tor_version: str | None = None
    bootstrap_phase: str | None = None
    bootstrap_progress: int | None = None
    control_auth_error: str | None = None


class TorServiceManager:
    _process_lock = Lock()

    def __init__(self, env: EnvironmentDetectionResult, detector: EnvironmentDetector, repository: DatabaseRepository):
        self.env = env
        self.detector = detector
        self.repository = repository
        self.pid_file = LOCAL_TOR_STATE_DIR / "tor.pid"
        self.state_file = LOCAL_TOR_STATE_DIR / "service_state.json"
        self.action_lock_path = LOCAL_TOR_STATE_DIR / "service_action.lock"

    def status(self) -> ServiceStatusResult:
        runtime = self.repository.fetch_runtime()
        runtime = self._reconcile_with_state_files(runtime)

        pid = runtime.get("pid")
        process_alive = self._pid_exists(pid)
        socks_port = int(runtime.get("socks_port") or 9050)
        control_port = int(runtime.get("control_port") or 9051)
        socks_open = self.detector.is_port_open("127.0.0.1", socks_port)
        control_open = self.detector.is_port_open("127.0.0.1", control_port)

        if not process_alive and runtime.get("status") in {"running", "starting", "restarting", "stopping"}:
            self._persist_runtime(
                status="failed" if runtime.get("status") != "stopping" else "stopped",
                phase="failed" if runtime.get("status") != "stopping" else "idle",
                last_error="Tor process not found for stored PID." if runtime.get("status") != "stopping" else None,
                pid=None,
                managed_by_tunator=0,
                last_seen_at=self._now_iso(),
            )
            self._cleanup_state_files()
            runtime = self.repository.fetch_runtime()

        control_info = self._probe_control(runtime)

        running = bool(process_alive and (socks_open or control_open or control_info.connected))
        if running and runtime.get("status") not in {"running", "starting", "restarting"}:
            self._persist_runtime(status="running", phase="ready" if socks_open else "verifying_ports", last_seen_at=self._now_iso(), last_error=None)
            runtime = self.repository.fetch_runtime()
        elif runtime.get("status") in {"starting", "restarting"} and process_alive:
            phase = "bootstrap_in_progress" if not socks_open else "ready"
            self._persist_runtime(phase=phase, last_seen_at=self._now_iso())
            runtime = self.repository.fetch_runtime()

        message = self._build_status_message(runtime, process_alive, socks_open, control_open, control_info)
        return ServiceStatusResult(
            running=running,
            source="runtime-db+pid-file+os-probe",
            message=message,
            pid=runtime.get("pid"),
            run_id=runtime.get("run_id"),
            status=runtime.get("status") or "stopped",
            phase=runtime.get("phase") or "idle",
            started_at=runtime.get("started_at"),
            last_seen_at=runtime.get("last_seen_at"),
            updated_at=runtime.get("updated_at"),
            last_error=runtime.get("last_error"),
            socks_port=socks_port,
            control_port=control_port,
            managed_by_tunator=bool(runtime.get("managed_by_tunator")),
            control_connected=control_info.connected,
            control_authenticated=control_info.authenticated,
            tor_version=control_info.tor_version,
            bootstrap_phase=control_info.bootstrap_phase,
            bootstrap_progress=control_info.bootstrap_progress,
            control_auth_error=control_info.auth_error,
        )

    def start(self, socks_port: int, control_port: int) -> ServiceActionResult:
        with self._action_lock("start"):
            return self._start_without_lock(socks_port=socks_port, control_port=control_port)

    def stop(self) -> ServiceActionResult:
        with self._action_lock("stop"):
            runtime = self.repository.fetch_runtime()
            pid = runtime.get("pid") or self._read_pid_file()
            run_id = runtime.get("run_id")
            return self._stop_without_lock(pid=pid, run_id=run_id)

    def restart(self, socks_port: int, control_port: int) -> ServiceActionResult:
        with self._action_lock("restart"):
            runtime = self.repository.fetch_runtime()
            pid = runtime.get("pid") or self._read_pid_file()
            run_id = runtime.get("run_id")
            self._persist_runtime(status="restarting", phase="stopping", last_seen_at=self._now_iso(), last_action="restart")

            stop_result = self._stop_without_lock(pid=pid, run_id=run_id)
            if not stop_result.success:
                return ServiceActionResult(False, "restart", stop_result.message, stop_result.pid, stop_result.run_id, stop_result.status, stop_result.phase)

            start_result = self._start_without_lock(socks_port=socks_port, control_port=control_port)
            start_result.action = "restart"
            return start_result

    def _wait_for_bootstrap(self, pid: int, socks_port: int, control_port: int, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._pid_exists(pid):
                return False
            if self.detector.is_port_open("127.0.0.1", socks_port):
                return True
            info = query_control_port(control_port, self._data_directory())
            if info.connected and info.authenticated and (info.bootstrap_progress or 0) >= 75:
                return True
            time.sleep(0.4)
        return False

    def _data_directory(self) -> str | None:
        if not self.env.torrc_path:
            return None
        torrc = Path(self.env.torrc_path)
        if not torrc.exists():
            return None
        for line in torrc.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("DataDirectory "):
                return line.split(maxsplit=1)[1].strip().strip('"')
        return None

    def _probe_control(self, runtime: dict[str, object]) -> ControlPortInfo:
        control_port = int(runtime.get("control_port") or 9051)
        return query_control_port(control_port=control_port, data_directory=self._data_directory())

    def _action_lock(self, action: str):
        class _Lock:
            def __init__(self, outer: TorServiceManager, lock_path: Path, action_name: str):
                self.outer = outer
                self.lock_path = lock_path
                self.action_name = action_name
                self.fd = None

            def __enter__(self):
                lock_acquired = self.outer._process_lock.acquire(blocking=False)
                if not lock_acquired:
                    raise RuntimeError("Outra ação de serviço já está em andamento")
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                self.fd = open(self.lock_path, "w", encoding="utf-8")
                self.fd.write(self.action_name)
                self.fd.flush()
                return self

            def __exit__(self, exc_type, exc, tb):
                if self.fd:
                    self.fd.close()
                self.outer._process_lock.release()

        return _Lock(self, self.action_lock_path, action)

    def _start_without_lock(self, socks_port: int, control_port: int) -> ServiceActionResult:
        current = self.status()
        if current.running:
            return ServiceActionResult(True, "start", "Tor já está em execução.", current.pid, current.run_id, current.status, current.phase)

        if not self.env.tor_binary_path:
            return self._fail_action("start", "Tor binary não encontrado.")
        if not self.env.torrc_path:
            return self._fail_action("start", "torrc não encontrado.")

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
            managed_by_tunator=1,
            last_action="start",
            last_action_message="starting",
        )

        verify = subprocess.run(
            [self.env.tor_binary_path, "--verify-config", "-f", self.env.torrc_path],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(Path(self.env.tor_binary_path).parent),
        )
        if verify.returncode != 0:
            output = (verify.stderr or verify.stdout or "Tor configuration validation failed.").strip()
            return self._fail_action("start", output, run_id=run_id)

        try:
            process = subprocess.Popen(
                [self.env.tor_binary_path, "-f", self.env.torrc_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=str(Path(self.env.tor_binary_path).parent),
            )
        except OSError as exc:
            return self._fail_action("start", f"Falha ao iniciar Tor: {exc}", run_id=run_id)

        self._write_pid_file(process.pid)
        self._write_state_file({"run_id": run_id, "pid": process.pid, "action": "start", "started_at": started_at})
        self._persist_runtime(pid=process.pid, phase="bootstrap_in_progress", last_seen_at=self._now_iso())

        boot_ok = self._wait_for_bootstrap(process.pid, socks_port, control_port, timeout=20)
        if not boot_ok:
            self._persist_runtime(status="starting", phase="bootstrap_in_progress", last_error="Bootstrap ainda em andamento")
            self.repository.record_service_event(run_id, "start", "starting", "bootstrap_in_progress", process.pid, "Processo iniciou, aguardando bootstrap")
            return ServiceActionResult(True, "start", "Processo Tor iniciou; bootstrap em andamento.", process.pid, run_id, "starting", "bootstrap_in_progress")

        self._persist_runtime(status="running", phase="ready", last_error=None, last_seen_at=self._now_iso())
        self.repository.record_service_event(run_id, "start", "running", "ready", process.pid, "Tor pronto para uso")
        return ServiceActionResult(True, "start", "Tor iniciado com sucesso.", process.pid, run_id, "running", "ready")

    def _stop_without_lock(self, pid: int | None, run_id: str | None) -> ServiceActionResult:
        self._persist_runtime(status="stopping", phase="stopping", last_seen_at=self._now_iso(), last_action="stop")
        if pid and self._pid_exists(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                deadline = time.time() + 8
                while time.time() < deadline and self._pid_exists(pid):
                    time.sleep(0.25)
                if self._pid_exists(pid):
                    os.kill(pid, signal.SIGKILL)
            except OSError as exc:
                return self._fail_action("stop", f"Erro ao parar processo: {exc}", run_id=run_id)

        self._cleanup_state_files()
        self._persist_runtime(
            status="stopped",
            phase="idle",
            pid=None,
            managed_by_tunator=0,
            last_seen_at=self._now_iso(),
            last_error=None,
            last_action_message="stopped",
        )
        self.repository.record_service_event(run_id, "stop", "stopped", "idle", None, "Tor parado")
        return ServiceActionResult(True, "stop", "Tor parado.", None, run_id, "stopped", "idle")

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

    def _build_status_message(self, runtime: dict[str, object], process_alive: bool, socks_open: bool, control_open: bool, control_info: ControlPortInfo) -> str:
        status = runtime.get("status") or "stopped"
        if status == "failed":
            err = runtime.get("last_error")
            return f"Falhou: {err}" if err else "Falha ao iniciar o Tor."
        if status in {"starting", "restarting"}:
            if control_info.connected and control_info.bootstrap_progress is not None:
                return f"Bootstrap em andamento ({control_info.bootstrap_progress}%)."
            return "Bootstrap em andamento."
        if process_alive and (socks_open or control_open):
            return "Tor em execução e portas respondendo."
        if process_alive:
            return "Processo Tor ativo; aguardando portas/control port."
        return "Tor parado."

    def _write_pid_file(self, pid: int) -> None:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(pid), encoding="utf-8")

    def _read_pid_file(self) -> int | None:
        if not self.pid_file.exists():
            return None
        raw = self.pid_file.read_text(encoding="utf-8").strip()
        return int(raw) if raw.isdigit() else None

    def _write_state_file(self, payload: dict[str, object]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(payload), encoding="utf-8")

    def _reconcile_with_state_files(self, runtime: dict[str, object]) -> dict[str, object]:
        pid_file_pid = self._read_pid_file()
        if pid_file_pid and not runtime.get("pid"):
            runtime["pid"] = pid_file_pid
            runtime["managed_by_tunator"] = 1
            self._persist_runtime(pid=pid_file_pid, managed_by_tunator=1)
        return runtime

    def _cleanup_state_files(self) -> None:
        for path in (self.pid_file, self.state_file):
            if path.exists():
                path.unlink()

    def _fail_action(self, action: str, message: str, run_id: str | None = None) -> ServiceActionResult:
        self._persist_runtime(status="failed", phase="failed", last_error=message, managed_by_tunator=0, last_action=action, last_action_message=message)
        self.repository.record_service_event(run_id, action, "failed", "failed", None, message)
        return ServiceActionResult(False, action, message, None, run_id, "failed", "failed")
