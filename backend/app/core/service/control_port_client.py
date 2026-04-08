from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ControlPortInfo:
    connected: bool
    authenticated: bool
    tor_version: str | None = None
    bootstrap_phase: str | None = None
    bootstrap_progress: int | None = None
    auth_error: str | None = None
    error: str | None = None


def query_control_port(control_port: int, data_directory: str | None = None) -> ControlPortInfo:
    try:
        from stem import SocketError
        from stem.connection import AuthenticationFailure
        from stem.control import Controller
    except Exception as exc:  # pragma: no cover - optional dependency path
        return ControlPortInfo(connected=False, authenticated=False, error=f"Stem unavailable: {exc}")

    try:
        with Controller.from_port(address="127.0.0.1", port=control_port) as controller:
            try:
                cookie_path = None
                if data_directory:
                    cookie_candidate = Path(data_directory) / "control_auth_cookie"
                    cookie_path = str(cookie_candidate) if cookie_candidate.exists() else None
                controller.authenticate(cookie_path=cookie_path)
            except AuthenticationFailure as auth_exc:
                return ControlPortInfo(connected=True, authenticated=False, auth_error=str(auth_exc))

            version = controller.get_version().version_str if controller.get_version() else None
            bootstrap = controller.get_info("status/bootstrap-phase", default=None)
            phase = None
            progress = None
            if bootstrap:
                # Example: NOTICE BOOTSTRAP PROGRESS=100 TAG=done SUMMARY="Done"
                phase = bootstrap
                for token in bootstrap.split():
                    if token.startswith("PROGRESS="):
                        raw = token.split("=", 1)[1].strip('"')
                        if raw.isdigit():
                            progress = int(raw)
            return ControlPortInfo(
                connected=True,
                authenticated=True,
                tor_version=version,
                bootstrap_phase=phase,
                bootstrap_progress=progress,
            )
    except (SocketError, socket.error) as exc:
        return ControlPortInfo(connected=False, authenticated=False, error=str(exc))
