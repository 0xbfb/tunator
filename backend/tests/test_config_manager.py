from pathlib import Path

from app.core.config.tor_config_manager import TorConfigManager


def test_read_parsed_config(tmp_path: Path) -> None:
    torrc = tmp_path / "torrc"
    torrc.write_text("SOCKSPort 9050\nControlPort 9051\n", encoding="utf-8")

    manager = TorConfigManager(str(torrc))
    parsed = manager.read_parsed()

    assert parsed["SOCKSPort"] == "9050"
    assert parsed["ControlPort"] == "9051"


def test_apply_updates_creates_new_values(tmp_path: Path) -> None:
    torrc = tmp_path / "torrc"
    torrc.write_text("SOCKSPort 9050\n", encoding="utf-8")

    manager = TorConfigManager(str(torrc))
    result = manager.apply_updates({"SOCKSPort": "9055", "ControlPort": "9051"})

    assert result["SOCKSPort"] == "9055"
    assert result["ControlPort"] == "9051"
    assert "SOCKSPort 9055" in torrc.read_text(encoding="utf-8")
