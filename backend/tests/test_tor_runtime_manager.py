from pathlib import Path

from app.core.vendor import tor_runtime_manager as mod
from app.core.vendor.tor_runtime_manager import TorRuntimeManager


def test_ensure_default_torrc_rewrites_stale_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mod, 'LOCAL_TOR_ARCHIVES_DIR', tmp_path / 'archives')
    monkeypatch.setattr(mod, 'LOCAL_TOR_RUNTIME_DIR', tmp_path / 'runtime')
    monkeypatch.setattr(mod, 'LOCAL_TOR_STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(mod, 'LOCAL_TOR_DATA_DIR', tmp_path / 'state' / 'data')
    monkeypatch.setattr(mod, 'LOCAL_TOR_LOG_DIR', tmp_path / 'state' / 'logs')
    monkeypatch.setattr(mod, 'LOCAL_TOR_TORRC_PATH', tmp_path / 'state' / 'torrc')

    manager = TorRuntimeManager()
    torrc = manager.torrc_path()
    torrc.parent.mkdir(parents=True, exist_ok=True)
    torrc.write_text(
        'SOCKSPort 9050\n'
        'ControlPort 9051\n'
        'DataDirectory /tmp/tunator_build/tunator/backend/vendor/tor/state/data\n'
        'Log notice file /tmp/tunator_build/tunator/backend/vendor/tor/state/logs/notices.log\n\n'
        '# Managed onion services\n'
        'HiddenServiceDir C:/x/onions/teste\n'
        'HiddenServicePort 80 127.0.0.1:3000\n',
        encoding='utf-8',
    )

    manager.ensure_default_torrc()
    raw = torrc.read_text(encoding='utf-8')

    assert '/tmp/tunator_build/' not in raw
    assert 'CookieAuthentication 1' in raw
    assert 'HiddenServiceDir C:/x/onions/teste' in raw
