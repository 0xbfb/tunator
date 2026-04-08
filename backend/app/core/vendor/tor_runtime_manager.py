from __future__ import annotations

import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.core.constants import (
    LOCAL_TOR_ARCHIVES_DIR,
    LOCAL_TOR_DATA_DIR,
    LOCAL_TOR_LOG_DIR,
    LOCAL_TOR_MANIFEST_PATH,
    LOCAL_TOR_RUNTIME_DIR,
    LOCAL_TOR_STATE_DIR,
    LOCAL_TOR_TORRC_PATH,
)


@dataclass(slots=True)
class TorBundleInfo:
    platform_key: str
    browser_version: str
    tor_version: str
    archive_name: str
    url: str
    signature_url: str | None = None


class TorRuntimeManager:
    def __init__(self) -> None:
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for path in [
            LOCAL_TOR_ARCHIVES_DIR,
            LOCAL_TOR_RUNTIME_DIR,
            LOCAL_TOR_STATE_DIR,
            LOCAL_TOR_DATA_DIR,
            LOCAL_TOR_LOG_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def platform_key(self) -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "windows" and machine in {"amd64", "x86_64"}:
            return "windows-x86_64"
        if system == "linux" and machine in {"amd64", "x86_64"}:
            return "linux-x86_64"
        if system == "darwin" and machine in {"arm64", "aarch64"}:
            return "macos-aarch64"
        if system == "darwin" and machine in {"x86_64", "amd64"}:
            return "macos-x86_64"
        return f"{system}-{machine}"

    def load_manifest(self) -> dict[str, dict[str, str]]:
        if not LOCAL_TOR_MANIFEST_PATH.exists():
            return {}
        return json.loads(LOCAL_TOR_MANIFEST_PATH.read_text(encoding="utf-8"))

    def supported_bundle(self) -> TorBundleInfo | None:
        manifest = self.load_manifest()
        item = manifest.get(self.platform_key())
        if not item:
            return None
        return TorBundleInfo(
            platform_key=self.platform_key(),
            browser_version=item["browser_version"],
            tor_version=item["tor_version"],
            archive_name=item["archive_name"],
            url=item["url"],
            signature_url=item.get("signature_url"),
        )

    def runtime_platform_dir(self) -> Path:
        return LOCAL_TOR_RUNTIME_DIR / self.platform_key()

    def torrc_path(self) -> Path:
        return LOCAL_TOR_TORRC_PATH

    def log_path(self) -> Path:
        return LOCAL_TOR_LOG_DIR / "notices.log"

    def data_dir(self) -> Path:
        return LOCAL_TOR_DATA_DIR

    def local_archive_path(self) -> Path | None:
        bundle = self.supported_bundle()
        if not bundle:
            return None
        candidate = LOCAL_TOR_ARCHIVES_DIR / bundle.archive_name
        return candidate if candidate.exists() else None

    def runtime_binary_path(self) -> Path | None:
        runtime_root = self.runtime_platform_dir()
        if not runtime_root.exists():
            return None

        for name in ("tor.exe", "tor"):
            matches = list(runtime_root.rglob(name))
            if matches:
                return matches[0]
        return None

    def geoip_path(self) -> Path | None:
        runtime_binary = self.runtime_binary_path()
        if not runtime_binary:
            return None
        candidate = runtime_binary.parent / "geoip"
        return candidate if candidate.exists() else None

    def geoip6_path(self) -> Path | None:
        runtime_binary = self.runtime_binary_path()
        if not runtime_binary:
            return None
        candidate = runtime_binary.parent / "geoip6"
        return candidate if candidate.exists() else None

    def _path_str(self, path: Path) -> str:
        return str(path.resolve()).replace("\\", "/")

    def render_default_torrc(self, socks_port: int = 9050, control_port: int = 9051) -> str:
        lines = [
            f"SOCKSPort {socks_port}",
            f"ControlPort {control_port}",
            f"DataDirectory {self._path_str(self.data_dir())}",
            f"Log notice file {self._path_str(self.log_path())}",
            "CookieAuthentication 1",
        ]
        geoip = self.geoip_path()
        geoip6 = self.geoip6_path()
        if geoip:
            lines.append(f"GeoIPFile {self._path_str(geoip)}")
        if geoip6:
            lines.append(f"GeoIPv6File {self._path_str(geoip6)}")
        return "\n".join(lines) + "\n"

    def _torrc_needs_refresh(self, torrc: Path) -> bool:
        if not torrc.exists():
            return True

        raw = torrc.read_text(encoding="utf-8", errors="ignore")
        state_root = self._path_str(LOCAL_TOR_STATE_DIR)
        data_dir = self._path_str(self.data_dir())
        log_path = self._path_str(self.log_path())
        geoip = self.geoip_path()
        geoip6 = self.geoip6_path()

        if "/tmp/tunator_build/" in raw:
            return True
        if f"DataDirectory {data_dir}" not in raw:
            return True
        if f"Log notice file {log_path}" not in raw:
            return True
        if "CookieAuthentication 1" not in raw:
            return True
        if geoip and f"GeoIPFile {self._path_str(geoip)}" not in raw:
            return True
        if geoip6 and f"GeoIPv6File {self._path_str(geoip6)}" not in raw:
            return True
        if "DataDirectory " in raw and state_root not in raw:
            return True
        return False

    def _normalize_torrc(self, torrc: Path) -> None:
        existing_lines = torrc.read_text(encoding="utf-8", errors="ignore").splitlines() if torrc.exists() else []
        skip_prefixes = (
            "SOCKSPort ",
            "ControlPort ",
            "DataDirectory ",
            "Log ",
            "CookieAuthentication ",
            "GeoIPFile ",
            "GeoIPv6File ",
        )
        preserved_lines = [line for line in existing_lines if not line.startswith(skip_prefixes)]

        content = self.render_default_torrc().rstrip("\n")
        preserved = "\n".join(preserved_lines).strip()
        if preserved:
            content = f"{content}\n\n{preserved}\n"
        else:
            content = f"{content}\n"
        torrc.write_text(content, encoding="utf-8")

    def ensure_default_torrc(self, overwrite: bool = False) -> Path:
        self.ensure_layout()
        torrc = self.torrc_path()
        if overwrite or self._torrc_needs_refresh(torrc):
            self._normalize_torrc(torrc)
        return torrc

    def extract_archive(self, archive_path: Path) -> Path:
        target = self.runtime_platform_dir()
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(target)
        self.ensure_default_torrc(overwrite=True)
        return target

    def download_bundle(self, destination: Path | None = None) -> Path:
        bundle = self.supported_bundle()
        if not bundle:
            raise RuntimeError(f"Unsupported platform for bundled Tor: {self.platform_key()}")

        destination = destination or (LOCAL_TOR_ARCHIVES_DIR / bundle.archive_name)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with urllib.request.urlopen(bundle.url, timeout=120) as response, tempfile.NamedTemporaryFile(delete=False) as temp_file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)
            temp_name = temp_file.name

        shutil.move(temp_name, destination)
        return destination

    def bootstrap_local_tor(self, archive_path: str | None = None, download_if_missing: bool = False) -> Path | None:
        self.ensure_default_torrc()

        current_binary = self.runtime_binary_path()
        if current_binary:
            self.ensure_default_torrc(overwrite=True)
            return current_binary

        local_archive: Path | None = None
        if archive_path:
            local_archive = Path(archive_path)
        else:
            detected_archive = self.local_archive_path()
            if detected_archive:
                local_archive = detected_archive
            elif download_if_missing or os.getenv("TUNATOR_AUTO_DOWNLOAD_TOR") == "1":
                local_archive = self.download_bundle()

        if local_archive and local_archive.exists():
            self.extract_archive(local_archive)
            return self.runtime_binary_path()

        return None

    def bundle_status(self) -> dict[str, str | bool | None]:
        bundle = self.supported_bundle()
        runtime_binary = self.runtime_binary_path()
        local_archive = self.local_archive_path()
        return {
            "platform_key": self.platform_key(),
            "supported": bundle is not None,
            "bundle_archive_name": bundle.archive_name if bundle else None,
            "bundle_url": bundle.url if bundle else None,
            "bundle_signature_url": bundle.signature_url if bundle else None,
            "browser_version": bundle.browser_version if bundle else None,
            "tor_version": bundle.tor_version if bundle else None,
            "archive_present": bool(local_archive),
            "archive_path": str(local_archive) if local_archive else None,
            "runtime_binary_present": bool(runtime_binary),
            "runtime_binary_path": str(runtime_binary) if runtime_binary else None,
            "torrc_path": str(self.torrc_path()),
            "log_path": str(self.log_path()),
            "data_dir": str(self.data_dir()),
        }
