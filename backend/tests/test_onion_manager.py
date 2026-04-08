from pathlib import Path

from app.core.config.tor_config_manager import TorConfigManager


def test_create_onion_service_updates_torrc(tmp_path: Path) -> None:
    torrc = tmp_path / 'torrc'
    torrc.write_text(
        'SOCKSPort 9050\n'
        'ControlPort 9051\n'
        f'DataDirectory {(tmp_path / "data").as_posix()}\n'
        f'Log notice file {(tmp_path / "notices.log").as_posix()}\n',
        encoding='utf-8',
    )

    manager = TorConfigManager(str(torrc))
    onion = manager.create_onion_service('Meu Site', 80, '127.0.0.1', 3000)
    text = torrc.read_text(encoding='utf-8')

    assert onion['name'] == 'meu-site'
    assert 'HiddenServiceDir' in text
    assert 'HiddenServicePort 80 127.0.0.1:3000' in text


def test_create_onion_service_with_password_enables_hidden_service_authorization(tmp_path: Path) -> None:
    torrc = tmp_path / 'torrc'
    torrc.write_text(
        'SOCKSPort 9050\n'
        'ControlPort 9051\n'
        f'DataDirectory {(tmp_path / "data").as_posix()}\n'
        f'Log notice file {(tmp_path / "notices.log").as_posix()}\n',
        encoding='utf-8',
    )

    manager = TorConfigManager(str(torrc))
    onion = manager.create_onion_service('Painel', 80, '127.0.0.1', 3000, 'segredo123')
    text = torrc.read_text(encoding='utf-8')

    assert onion['auth_enabled'] is True
    assert onion['auth_client_name'] is not None
    assert f"HiddenServiceAuthorizeClient basic {onion['auth_client_name']}" in text
