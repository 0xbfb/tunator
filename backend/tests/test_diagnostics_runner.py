from pathlib import Path

from app.core.config.tor_config_manager import TorConfigManager
from app.core.detection.environment_detector import EnvironmentDetectionResult, EnvironmentDetector
from app.core.diagnostics.diagnostics_runner import DiagnosticsRunner
from app.core.service.tor_service_manager import TorServiceManager
from app.db.repository import DatabaseRepository


def test_diagnostics_include_runtime_support_flag(tmp_path: Path) -> None:
    torrc = tmp_path / "torrc"
    torrc.write_text("SOCKSPort 9050\nControlPort 9051\n", encoding="utf-8")

    env = EnvironmentDetectionResult(
        os_name="linux",
        tor_binary_path=None,
        torrc_path=str(torrc),
        log_path=None,
        service_name=None,
        tor_installed=False,
        service_available=False,
        tor_source="missing",
        vendor_root=str(tmp_path),
        supported_platform=True,
        bundle_archive_path=None,
        bundle_download_url="https://example.org/tor-bundle.tar.gz",
    )

    detector = EnvironmentDetector(torrc_env=str(torrc))
    repo = DatabaseRepository(db_path=str(tmp_path / "test.db"))
    repo.init_db()
    manager = TorServiceManager(env, detector, repo)
    config_manager = TorConfigManager(str(torrc))
    runner = DiagnosticsRunner(env, detector, manager, config_manager)

    result = runner.run()
    names = {check.name for check in result.checks}

    assert "runtime_platform_supported" in names
    assert "tor_binary_detected" in names
    assert "service_running" in names
    assert any(getattr(check, "recommendation", None) for check in result.checks)
