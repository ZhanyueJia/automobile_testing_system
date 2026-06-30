from __future__ import annotations

from common.config.config_manager import ConfigManager


def test_config_manager_instances_do_not_share_mutable_state() -> None:
    first = ConfigManager()
    second = ConfigManager()

    first.set("runtime.flags", {"enabled": True})

    assert second.get("runtime.flags") is None


def test_config_reads_return_deep_copies() -> None:
    cfg = ConfigManager()
    cfg.set("vehicle.sensors", {"camera": {"count": 6}})

    value = cfg.get("vehicle.sensors")
    value["camera"]["count"] = 8

    raw = cfg.raw
    raw["vehicle"]["sensors"]["camera"]["count"] = 12

    assert cfg.get("vehicle.sensors.camera.count") == 6


def test_load_resets_previous_values() -> None:
    cfg = ConfigManager()
    cfg.set("temporary.value", "stale")

    cfg.load(env="ci")

    assert cfg.get("env") == "ci"
    assert cfg.get("temporary.value") is None
