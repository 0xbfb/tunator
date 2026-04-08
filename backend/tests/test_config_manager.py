from pathlib import Path

from app.core.config.tor_config_manager import TorConfigManager


def test_apply_updates_creates_new_values(tmp_path: Path) -> None:
    torrc = tmp_path / 'torrc'
    torrc.write_text('SOCKSPort 9050\n', encoding='utf-8')

    manager = TorConfigManager(str(torrc))
    result = manager.apply_updates({'SOCKSPort': '9055', 'ControlPort': '9051'})

    assert result['SOCKSPort'] == '9055'
    assert result['ControlPort'] == '9051'
    text = torrc.read_text(encoding='utf-8')
    assert 'SOCKSPort 9055' in text
    assert '# BEGIN TUNATOR MANAGED' in text


def test_preview_has_diff(tmp_path: Path) -> None:
    torrc = tmp_path / 'torrc'
    torrc.write_text('SOCKSPort 9050\n', encoding='utf-8')
    manager = TorConfigManager(str(torrc))
    preview = manager.preview_updates({'SOCKSPort': '9060'})
    assert preview['valid'] is True
    assert '9060' in str(preview['diff'])


def test_restore_backup(tmp_path: Path) -> None:
    torrc = tmp_path / 'torrc'
    torrc.write_text('SOCKSPort 9050\n', encoding='utf-8')
    manager = TorConfigManager(str(torrc))
    backup = manager.create_backup()
    manager.apply_updates({'SOCKSPort': '9059'})
    manager.restore_backup(Path(str(backup)).name)
    assert 'SOCKSPort 9050' in torrc.read_text(encoding='utf-8')
