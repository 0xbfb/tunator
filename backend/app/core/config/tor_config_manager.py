from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.constants import LOCAL_TOR_ONIONS_DIR, SUPPORTED_TORRC_OPTIONS

MANAGED_BEGIN = "# BEGIN TUNATOR MANAGED"
MANAGED_END = "# END TUNATOR MANAGED"


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
        assert self.torrc_path
        root = Path(self.torrc_path).parent
        return {
            "SOCKSPort": "9050",
            "ControlPort": "9051",
            "DataDirectory": str((root / "data").resolve()).replace("\\", "/"),
            "Log": str(f"notice file {(root / 'logs' / 'notices.log').resolve()}").replace("\\", "/"),
            "CookieAuthentication": "1",
        }

    def parse_model(self) -> dict[str, list[dict[str, str | int | bool | None]] | dict[str, str]]:
        base_options = self._default_base_options() if self.torrc_path else {}
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
                current_onion = OnionService(name=name, directory=directory, public_port=80, target_host="127.0.0.1", target_port=80, hostname=hostname, hostname_path=hostname_path, hostname_ready=hostname_ready)
                onion_services.append(current_onion)
                continue

            if key == "HiddenServicePort" and current_onion is not None:
                match = re.match(r"^(\d+)\s+([^:]+):(\d+)$", value)
                if match:
                    current_onion.public_port = int(match.group(1))
                    current_onion.target_host = match.group(2)
                    current_onion.target_port = int(match.group(3))
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

        return {"base_options": base_options, "onion_services": [self._onion_to_dict(item) for item in onion_services]}

    def read_parsed(self) -> dict[str, str]:
        return self.parse_model()["base_options"]  # type: ignore[return-value]

    def list_onion_services(self) -> list[dict[str, str | int | bool | None]]:
        return self.parse_model()["onion_services"]  # type: ignore[return-value]

    def validate_updates(self, updates: dict[str, str], advanced_mode: bool = False) -> ConfigValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        editable = SUPPORTED_TORRC_OPTIONS | {"CookieAuthentication", "GeoIPFile", "GeoIPv6File"}

        for key, value in updates.items():
            if key not in editable:
                errors.append(f"Unsupported option: {key}")
                continue
            if key in {"HiddenServiceDir", "HiddenServicePort"}:
                warnings.append(f"{key} is managed by the onion service UI")
                continue
            normalized = str(value).strip()
            if key != "ExcludeNodes" and not normalized:
                errors.append(f"Value for {key} cannot be empty")
            if key in {"SOCKSPort", "ControlPort"}:
                if not normalized.isdigit() or not (1 <= int(normalized) <= 65535):
                    errors.append(f"{key} must be numeric and between 1 and 65535")
            if key == "DataDirectory" and normalized:
                if not Path(normalized).is_absolute():
                    warnings.append("DataDirectory should be an absolute path")
            if key == "Log" and "file" not in normalized.lower():
                warnings.append("Using Log notice file ... is recommended")
            if key == "ExcludeNodes":
                if normalized and not re.fullmatch(r"(\{[a-zA-Z]{2}\})(,\{[a-zA-Z]{2}\})*", normalized):
                    warnings.append("ExcludeNodes format expected: {ru},{cn}")

        sensitive = {"GeoIPFile", "GeoIPv6File"}
        if not advanced_mode and any(key in sensitive for key in updates):
            errors.append("Sensitive options require advanced_mode=true")

        return ConfigValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def validate_onion_service(self, name: str, public_port: int, target_host: str, target_port: int, access_password: str | None = None) -> ConfigValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        safe_name = self._sanitize_onion_name(name)
        if not safe_name:
            errors.append("Onion service name cannot be empty")
        if safe_name != name.strip().lower():
            warnings.append(f"Folder name normalized to {safe_name}")
        for port_name, value in [("public_port", public_port), ("target_port", target_port)]:
            if value < 1 or value > 65535:
                errors.append(f"{port_name} must be between 1 and 65535")
        if target_host.strip() not in {"127.0.0.1", "localhost"}:
            warnings.append("Target host should usually be local (127.0.0.1/localhost)")
        existing_names = {str(item["name"]) for item in self.list_onion_services()}
        if safe_name in existing_names:
            errors.append(f"An onion service named {safe_name} already exists")
        normalized_password = (access_password or "").strip()
        if normalized_password and len(normalized_password) < 6:
            errors.append("Password must have at least 6 characters")
        return ConfigValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def list_backups(self) -> list[dict[str, str | int | None]]:
        if not self.torrc_path:
            return []
        path = Path(self.torrc_path)
        parent = path.parent
        backups = sorted(parent.glob(f"{path.name}.bak.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [
            {
                "name": item.name,
                "path": str(item),
                "size_bytes": item.stat().st_size,
                "created_at": datetime.fromtimestamp(item.stat().st_mtime, timezone.utc).isoformat(),
            }
            for item in backups
        ]

    def create_backup(self) -> str | None:
        if not self.torrc_path:
            return None
        path = Path(self.torrc_path)
        if not path.exists():
            return None
        backup_path = path.with_name(f"{path.name}.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(path, backup_path)
        return str(backup_path)

    def restore_backup(self, backup_name: str) -> dict[str, str]:
        if not self.torrc_path:
            raise ValueError("torrc path is not configured")
        path = Path(self.torrc_path)
        candidate = path.parent / backup_name
        if not candidate.exists():
            raise ValueError(f"Backup {backup_name} not found")
        content = candidate.read_text(encoding="utf-8")
        self._atomic_write(content)
        return {"restored_from": str(candidate), "torrc_path": str(path)}

    def preview_updates(self, updates: dict[str, str], advanced_mode: bool = False) -> dict[str, object]:
        validation = self.validate_updates(updates, advanced_mode=advanced_mode)
        if not validation.valid:
            return {"valid": False, "errors": validation.errors, "warnings": validation.warnings, "diff": ""}
        before = self.read_raw()
        model = self.parse_model()
        base_options = dict(model["base_options"])  # type: ignore[arg-type]
        for key, value in updates.items():
            normalized = str(value).strip()
            if key == "ExcludeNodes" and not normalized:
                base_options.pop(key, None)
            else:
                base_options[key] = normalized
        after = self._render_model(base_options, model["onion_services"])  # type: ignore[arg-type]
        diff = "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile="torrc(before)", tofile="torrc(after)", lineterm=""))
        return {"valid": True, "errors": [], "warnings": validation.warnings, "diff": diff, "after": after}

    def apply_updates(self, updates: dict[str, str], advanced_mode: bool = False) -> dict[str, str]:
        validation = self.validate_updates(updates, advanced_mode=advanced_mode)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        model = self.parse_model()
        base_options = dict(model["base_options"])  # type: ignore[arg-type]
        for key, value in updates.items():
            normalized = str(value).strip()
            if key == "ExcludeNodes" and not normalized:
                base_options.pop(key, None)
                continue
            base_options[key] = normalized
        content = self._render_model(base_options, model["onion_services"])  # type: ignore[arg-type]
        self._atomic_write(content)
        return self.read_parsed()

    def create_onion_service(self, name: str, public_port: int, target_host: str, target_port: int, access_password: str | None = None) -> dict[str, str | int | bool | None]:
        validation = self.validate_onion_service(name, public_port, target_host, target_port, access_password)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        safe_name = self._sanitize_onion_name(name)
        normalized_password = (access_password or "").strip()
        auth_client_name = self._build_auth_client_name(safe_name, normalized_password) if normalized_password else None
        service_dir = self._ensure_onions_root() / safe_name
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
        self._atomic_write(self._render_model(model["base_options"], onion_services))  # type: ignore[arg-type]
        return onion

    def remove_onion_service(self, name: str, remove_directory: bool = False) -> dict[str, str | bool]:
        safe_name = self._sanitize_onion_name(name)
        model = self.parse_model()
        onion_services = list(model["onion_services"])
        removed_item = next((item for item in onion_services if item["name"] == safe_name), None)
        remaining = [item for item in onion_services if item["name"] != safe_name]
        if not removed_item:
            raise ValueError(f"Onion service {safe_name} was not found")
        self._atomic_write(self._render_model(model["base_options"], remaining))  # type: ignore[arg-type]
        if remove_directory:
            directory = Path(str(removed_item["directory"]))
            if directory.exists():
                shutil.rmtree(directory)
        return {"name": safe_name, "removed": True}

    def _render_model(self, base_options: dict[str, str], onion_services: list[dict[str, str | int | bool | None]]) -> str:
        existing = self.read_raw().splitlines()
        prefix_lines = self._extract_unmanaged_prefix(existing)
        suffix_lines = self._extract_unmanaged_suffix(existing)

        lines = []
        ordered_base = ["SOCKSPort", "ControlPort", "DataDirectory", "Log", "ExcludeNodes", "CookieAuthentication", "GeoIPFile", "GeoIPv6File"]
        for key in ordered_base:
            if key in base_options:
                lines.append(f"{key} {base_options[key]}")
        for key in sorted(base_options.keys()):
            if key not in ordered_base:
                lines.append(f"{key} {base_options[key]}")

        lines.append("")
        lines.append(MANAGED_BEGIN)
        lines.append("# Managed onion services")
        for item in onion_services:
            lines.append(f"HiddenServiceDir {item['directory']}")
            lines.append(f"HiddenServicePort {item['public_port']} {item['target_host']}:{item['target_port']}")
            if item.get("auth_enabled") and item.get("auth_client_name"):
                lines.append(f"HiddenServiceAuthorizeClient basic {item['auth_client_name']}")
            lines.append("")
        lines.append(MANAGED_END)

        content_parts = []
        if prefix_lines:
            content_parts.extend(prefix_lines)
        content_parts.extend(lines)
        if suffix_lines:
            content_parts.extend(suffix_lines)
        return "\n".join([line for line in content_parts]).strip() + "\n"

    def _extract_unmanaged_prefix(self, lines: list[str]) -> list[str]:
        if MANAGED_BEGIN in lines:
            idx = lines.index(MANAGED_BEGIN)
            return lines[:idx]
        return []

    def _extract_unmanaged_suffix(self, lines: list[str]) -> list[str]:
        if MANAGED_END in lines:
            idx = lines.index(MANAGED_END)
            return lines[idx + 1 :]
        return []

    def _atomic_write(self, content: str) -> None:
        if not self.torrc_path:
            raise ValueError("torrc path is not configured")
        target = Path(self.torrc_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)

    def _ensure_onions_root(self) -> Path:
        LOCAL_TOR_ONIONS_DIR.mkdir(parents=True, exist_ok=True)
        return LOCAL_TOR_ONIONS_DIR

    def _sanitize_onion_name(self, name: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-._")
        return safe.lower()

    def _build_auth_client_name(self, safe_name: str, password: str) -> str:
        digest = hashlib.sha1(password.encode("utf-8")).hexdigest()[:10]
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
