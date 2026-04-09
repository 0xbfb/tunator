from __future__ import annotations

from pathlib import Path

import pytest

from app.services.tunator_service import TunatorService


@pytest.fixture()
def temp_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    torrc = tmp_path / "torrc"
    torrc.write_text(
        "SOCKSPort 9050\n"
        "ControlPort 9051\n"
        "DataDirectory /tmp/tunator-data\n"
        "Log notice file /tmp/tunator.log\n",
        encoding="utf-8",
    )

    log = tmp_path / "tor.log"
    log.write_text("[notice] Bootstrapped 100%\n", encoding="utf-8")

    db = tmp_path / "tunator.db"

    monkeypatch.setenv("TUNATOR_TORRC_PATH", str(torrc))
    monkeypatch.setenv("TUNATOR_LOG_PATH", str(log))
    monkeypatch.setenv("TUNATOR_DB_PATH", str(db))
    monkeypatch.delenv("TUNATOR_TOR_BINARY", raising=False)
    monkeypatch.delenv("TUNATOR_AUTO_DOWNLOAD_TOR", raising=False)

    return {"torrc": torrc, "log": log, "db": db}


@pytest.fixture()
def service(temp_paths: dict[str, Path]) -> TunatorService:
    return TunatorService.bootstrap()
