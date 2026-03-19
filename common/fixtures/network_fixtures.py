"""
network_fixtures - 网络通信相关 pytest 共享夹具
"""
from __future__ import annotations

import pytest

from common.config.config_manager import ConfigManager
from common.utils.logger import get_logger

logger = get_logger("fixtures.network")


@pytest.fixture(scope="session")
def adb_config(config: ConfigManager) -> dict:
    """ADB 连接配置"""
    return {
        "host": config.get("adb.default_host", "127.0.0.1"),
        "port": config.get("adb.default_port", 5037),
        "connect_timeout": config.get("adb.connect_timeout", 10),
        "command_timeout": config.get("adb.command_timeout", 30),
    }


@pytest.fixture(scope="session")
def can_config(config: ConfigManager) -> dict:
    """CAN 总线配置"""
    return {
        "interface": config.get("can.default_interface", "socketcan"),
        "channel": config.get("can.default_channel", "can0"),
        "bitrate": config.get("can.default_bitrate", 500000),
    }