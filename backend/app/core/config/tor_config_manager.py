from __future__ import annotations

import re
import shutil
from hashlib import sha1
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.constants import LOCAL_TOR_ONIONS_DIR, SUPPORTED_TORRC_OPTIONS


@dataclass(slots=True)
class ConfigValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


@dataclass(slots=True)
class OnionService:
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


class TorConfigManager:
    def __init__(self, torrc_path: str | None):
        self.torrc_path = torrc_path

    def read_raw(self) -> str:
        if not self.torrc_path:
            return ""
        path = Path(self.torrc_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _default_base_options(self) -> dict[str, str]:
        return {
            "SOCKSPort": "9050",
            "ControlPort": "9051",
            "DataDirectory": str((Path(self.torrc_path).parent / "data").resolve()).replace("\\", "/"),
            "Log": str(f"notice file {(Path(self.torrc_path).parent / 'logs' / 'notices.log').resolve()}").replace("\\", "/"),
            "CookieAuthentication": "1",
        }

    def parse_model(self) -> dict[str, list[dict[str, str | int | bool | None]] | dict[str, str]]:
        base_options = self._default_base_options()
        onion_services: list[OnionService] = []
        current_onion: OnionService | None = None

        for raw_line in self.read_raw().splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split(maxsplit=1)
            key = parts[0]
            value = parts[1].strip() if len(parts) > 1 else ""

            if key == "HiddenServiceDir":
                directory = value.strip().strip('"')
                name = Path(directory).name or f"onion-{len(onion_services)+1}"
                hostname, hostname_path, hostname_ready = self._read_hostname(directory)
                current_onion = OnionService(
                    name=name,
                    directory=directory,
                    public_port=80,
                    target_host="127.0.0.1",
                    target_port=80,
                    hostname=hostname,
                    hostname_path=hostname_path,
                    hostname_ready=hostname_ready,
                )
                onion_services.append(current_onion)
                continue

            if key == "HiddenServicePort" and current_onion is not None:
                match = re.match(r"^(\d+)\s+([^:]+):(\d+)$", value)
                if match:
                    current_onion.public_port = int(match.group(1))
                    current_onion.target_host = match.group(2)
                    current_onion.target_port = int(match.group(3))
                else:
                    parts = value.split()
                    if len(parts) >= 2 and parts[0].isdigit() and ":" in parts[1]:
                        host, port = parts[1].rsplit(":", 1)
                        current_onion.target_host = host
                        current_onion.public_port = int(parts[0])
                        if port.isdigit():
                            current_onion.target_port = int(port)
                continue

            if key == "HiddenServiceAuthorizeClient" and current_onion is not None:
                auth_match = re.match(r"^(basic|stealth)\s+(.+)$", value)
                if auth_match:
                    clients = [item.strip() for item in auth_match.group(2).split(",") if item.strip()]
                    current_onion.auth_enabled = bool(clients)
                    current_onion.auth_client_name = clients[0] if clients else None
                continue

            if key not in {"HiddenServiceDir", "HiddenServicePort"}:
                base_options[key] = value

        return {
            "base_options": base_options,
            "onion_services": [self._onion_to_dict(item) for item in onion_services],
        }

    def read_parsed(self) -> dict[str, str]:
        return self.parse_model()["base_options"]  # type: ignore[return-value]

    def list_onion_services(self) -> list[dict[str, str | int | bool | None]]:
        return self.parse_model()["onion_services"]  # type: ignore[return-value]

    def validate_updates(self, updates: dict[str, str]) -> ConfigValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        editable = SUPPORTED_TORRC_OPTIONS | {"CookieAuthentication", "GeoIPFile", "GeoIPv6File"}
        for key, value in updates.items():
            if key not in editable:
                errors.append(f"Unsupported option: {key}")
                continue
            if key in {"HiddenServiceDir", "HiddenServicePort"}:
                warnings.append(f"{key} is managed by the onion service UI and is better edited there")
                continue
            if key == "ExcludeNodes" and not str(value).strip():
                continue
            if not str(value).strip():
                errors.append(f"Value for {key} cannot be empty")

        for numeric_key in ("SOCKSPort", "ControlPort"):
            if numeric_key in updates and not str(updates[numeric_key]).isdigit():
                errors.append(f"{numeric_key} must be numeric")

        if "DataDirectory" in updates:
            data_dir = Path(str(updates["DataDirectory"]))
            if data_dir.suffix:
                warnings.append("DataDirectory usually points to a directory, not a file")

        if "Log" in updates and "file" not in str(updates["Log"]).lower():
            warnings.append("Using a file target in Log is recommended for local diagnostics")

        if "ExcludeNodes" in updates:
            normalized = str(updates["ExcludeNodes"]).strip()
            if normalized and "{" not in normalized:
                warnings.append("Use country codes in braces for ExcludeNodes, e.g. {ru},{cn}")

        return ConfigValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def validate_onion_service(
        self,
        name: str,
        public_port: int,
        target_host: str,
        target_port: int,
        access_password: str | None = None,
    ) -> ConfigValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        safe_name = self._sanitize_onion_name(name)
        if not safe_name:
            errors.append("Onion service name cannot be empty")
        if safe_name != name.strip():
            warnings.append(f"Folder name normalized to {safe_name}")
        for port_name, value in [("public_port", public_port), ("target_port", target_port)]:
            if value < 1 or value > 65535:
                errors.append(f"{port_name} must be between 1 and 65535")
        if not target_host.strip():
            errors.append("target_host cannot be empty")
        existing_names = {str(item["name"]) for item in self.list_onion_services()}
        if safe_name in existing_names:
            errors.append(f"An onion service named {safe_name} already exists")
        normalized_password = (access_password or "").strip()
        if normalized_password and len(normalized_password) < 6:
            errors.append("Password must have at least 6 characters")
        return ConfigValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def create_backup(self) -> str | None:
        if not self.torrc_path:
            return None
        path = Path(self.torrc_path)
        if not path.exists():
            return None
        backup_path = path.with_suffix(path.suffix + f".bak.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(path, backup_path)
        return str(backup_path)

    def apply_updates(self, updates: dict[str, str]) -> dict[str, str]:
        validation = self.validate_updates(updates)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        model = self.parse_model()
        base_options = model["base_options"]  # type: ignore[assignment]
        for key, value in updates.items():
            if key in {"HiddenServiceDir", "HiddenServicePort"}:
                continue
            normalized = str(value).strip()
            if key == "ExcludeNodes" and not normalized:
                base_options.pop(key, None)
                continue
            base_options[key] = normalized  # type: ignore[index]
        self._write_model(base_options, model["onion_services"])
        return self.read_parsed()

    def create_onion_service(
        self,
        name: str,
        public_port: int,
        target_host: str,
        target_port: int,
        access_password: str | None = None,
    ) -> dict[str, str | int | bool | None]:
        validation = self.validate_onion_service(name, public_port, target_host, target_port, access_password)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        safe_name = self._sanitize_onion_name(name)
        normalized_password = (access_password or "").strip()
        auth_client_name = self._build_auth_client_name(safe_name, normalized_password) if normalized_password else None
        onions_root = self._ensure_onions_root()
        service_dir = onions_root / safe_name
        service_dir.mkdir(parents=True, exist_ok=True)

        model = self.parse_model()
        onion = {
            "name": safe_name,
            "directory": str(service_dir),
            "public_port": int(public_port),
            "target_host": target_host.strip(),
            "target_port": int(target_port),
            "hostname": None,
            "hostname_path": str(service_dir / "hostname"),
            "hostname_ready": False,
            "auth_enabled": bool(auth_client_name),
            "auth_client_name": auth_client_name,
        }
        onion_services = list(model["onion_services"])
        onion_services.append(onion)
        self._write_model(model["base_options"], onion_services)
        return onion

    def remove_onion_service(self, name: str) -> dict[str, str | bool]:
        safe_name = self._sanitize_onion_name(name)
        model = self.parse_model()
        onion_services = list(model["onion_services"])
        remaining = [item for item in onion_services if item["name"] != safe_name]
        if len(remaining) == len(onion_services):
            raise ValueError(f"Onion service {safe_name} was not found")
        self._write_model(model["base_options"], remaining)
        return {"name": safe_name, "removed": True}

    def _write_model(self, base_options: dict[str, str], onion_services: list[dict[str, str | int | bool | None]]) -> None:
        if not self.torrc_path:
            raise ValueError("torrc path is not configured")
        lines = []
        ordered_base = ["SOCKSPort", "ControlPort", "DataDirectory", "Log", "ExcludeNodes", "CookieAuthentication", "GeoIPFile", "GeoIPv6File"]
        for key in ordered_base:
            if key in base_options:
                lines.append(f"{key} {base_options[key]}")
        for key in sorted(base_options.keys()):
            if key not in ordered_base:
                lines.append(f"{key} {base_options[key]}")
        if onion_services:
            lines.append("")
            lines.append("# Managed onion services")
            for item in onion_services:
                lines.append(f"HiddenServiceDir {item['directory']}")
                lines.append(f"HiddenServicePort {item['public_port']} {item['target_host']}:{item['target_port']}")
                if item.get("auth_enabled") and item.get("auth_client_name"):
                    lines.append(f"HiddenServiceAuthorizeClient basic {item['auth_client_name']}")
                lines.append("")
        Path(self.torrc_path).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def _ensure_onions_root(self) -> Path:
        onion_root = LOCAL_TOR_ONIONS_DIR
        onion_root.mkdir(parents=True, exist_ok=True)
        return onion_root

    def _sanitize_onion_name(self, name: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-._")
        return safe.lower()

    def _build_auth_client_name(self, safe_name: str, password: str) -> str:
        digest = sha1(password.encode("utf-8")).hexdigest()[:10]
        return f"{safe_name}-{digest}"

    def _read_hostname(self, directory: str) -> tuple[str | None, str | None, bool]:
        service_dir = Path(directory)
        hostname_path = service_dir / "hostname"
        if hostname_path.exists():
            hostname = hostname_path.read_text(encoding="utf-8", errors="ignore").strip() or None
            return hostname, str(hostname_path), bool(hostname)
        return None, str(hostname_path), False

    def _onion_to_dict(self, item: OnionService) -> dict[str, str | int | bool | None]:
        return {
            "name": item.name,
            "directory": item.directory,
            "public_port": item.public_port,
            "target_host": item.target_host,
            "target_port": item.target_port,
            "hostname": item.hostname,
            "hostname_path": item.hostname_path,
            "hostname_ready": item.hostname_ready,
            "auth_enabled": item.auth_enabled,
            "auth_client_name": item.auth_client_name,
        }
