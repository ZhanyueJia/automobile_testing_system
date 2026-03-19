"""
conftest.py - 车门系统测试的局部 fixtures
提供 CAN-FD 驱动、车门控制配置等夹具
"""
from __future__ import annotations

import pytest

from common.config.config_manager import ConfigManager
from common.utils.logger import get_logger
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver

logger = get_logger("fixtures.door_system")


@pytest.fixture(scope="module")
def can(config: ConfigManager) -> CANFDDriver:
    """
    CAN-FD 驱动 (module 级别共享)
    根据环境配置自动选择 Mock 或真机模式
    """
    env = config.get("env", "simulation")
    is_mock = env in ("simulation", "ci")

    driver = CANFDDriver(
        interface=config.get("can.interface", "socketcan"),
        channel=config.get("can.channel", "can0"),
        bitrate=config.get("can.bitrate", 500000),
        fd=config.get("can.fd_enabled", True),
        data_bitrate=config.get("can.data_bitrate", 2000000),
        mock=is_mock,
    )
    driver.connect()
    logger.info(f"CAN-FD driver ready (mock={is_mock})")
    yield driver
    driver.disconnect()


@pytest.fixture(scope="module")
def door_config(config: ConfigManager) -> dict:
    """车门系统测试配置参数"""
    return {
        # CAN 信号 ID
        "central_lock_cmd_id": config.get(
            "vcu.body_control.door.central_lock_cmd_id", 0x310
        ),
        "central_lock_status_id": config.get(
            "vcu.body_control.door.central_lock_status_id", 0x311
        ),
        "door_status_id": config.get(
            "vcu.body_control.door.door_status_id", 0x312
        ),
        # 超时与阈值
        "lock_response_timeout_ms": config.get(
            "vcu.body_control.door.lock_response_timeout_ms", 500
        ),
        "unlock_response_timeout_ms": config.get(
            "vcu.body_control.door.unlock_response_timeout_ms", 500
        ),
        "max_response_time_ms": config.get(
            "vcu.body_control.door.max_response_time_ms", 300
        ),
        "test_cycles": config.get(
            "vcu.body_control.door.test_cycles", 50
        ),
        # 车门列表
        "doors": config.get(
            "vcu.body_control.door.doors",
            ["front_left", "front_right", "rear_left", "rear_right"],
        ),
        # 速度阈值 (km/h) - 超过此速度自动落锁
        "auto_lock_speed_kmh": config.get(
            "vcu.body_control.door.auto_lock_speed_kmh", 20
        ),
    }