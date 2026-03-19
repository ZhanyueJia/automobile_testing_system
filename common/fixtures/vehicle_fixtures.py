"""
vehicle_fixtures - 车辆相关 pytest 共享夹具
提供车辆连接、配置加载、状态检查等复用 fixture
"""
from __future__ import annotations

import pytest

from common.config.config_manager import ConfigManager
from common.utils.logger import get_logger

logger = get_logger("fixtures.vehicle")


@pytest.fixture(scope="session")
def config() -> ConfigManager:
    """会话级配置管理器"""
    cfg = ConfigManager()
    vehicle = pytest.config_vehicle_model if hasattr(pytest, "config_vehicle_model") else "default"
    env = pytest.config_env if hasattr(pytest, "config_env") else "simulation"
    cfg.load(vehicle_model=vehicle, env=env)
    logger.info(f"配置已加载: vehicle={vehicle}, env={env}")
    return cfg


@pytest.fixture(scope="session")
def vehicle_model(config: ConfigManager) -> str:
    """当前测试车型名称"""
    return config.get_vehicle("model", "default")


@pytest.fixture(scope="session")
def vehicle_config(config: ConfigManager) -> dict:
    """当前车型完整配置"""
    return config.get_vehicle()