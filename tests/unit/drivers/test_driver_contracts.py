from __future__ import annotations

import subprocess

import pytest

from drivers.protocol_drivers.adb_driver import ADBDriver
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver, CANMessage


class Completed:
    returncode = 0
    stderr = ""
    stdout = "ok\n"


def test_adb_command_runner_uses_argument_list(monkeypatch) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args: list[str], **kwargs):
        calls.append((args, kwargs))
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    driver = ADBDriver(serial="device 1", command_timeout=7)

    output = driver._run_adb_cmd(["push", "C:/tmp/file name.txt", "/sdcard/file name.txt"])

    assert output == "ok"
    assert calls == [
        (
            ["adb", "-s", "device 1", "push", "C:/tmp/file name.txt", "/sdcard/file name.txt"],
            {"capture_output": True, "text": True, "timeout": 7},
        )
    ]


def test_adb_mock_lifecycle_and_shell_helpers() -> None:
    driver = ADBDriver(mock=True)

    driver.connect()

    assert driver.is_connected is True
    assert driver.get_voice_assistant_state() == "listening"
    assert driver.is_app_running("com.example.app") is True

    driver.disconnect()

    assert driver.is_connected is False


def test_can_mock_lifecycle_send_receive_contract() -> None:
    driver = CANFDDriver(mock=True)
    msg = CANMessage(arbitration_id=0x123, data=b"\x01\x02")

    driver.connect()
    driver.send(msg)

    assert driver.is_connected is True
    assert driver.receive(timeout=0.01) is None

    driver.disconnect()

    assert driver.is_connected is False


def test_can_real_mode_requires_connection_before_io() -> None:
    driver = CANFDDriver(mock=False)
    msg = CANMessage(arbitration_id=0x123, data=b"\x01")

    with pytest.raises(RuntimeError, match="CAN 总线未连接"):
        driver.send(msg)

    with pytest.raises(RuntimeError, match="CAN 总线未连接"):
        driver.receive(timeout=0.01)
