"""
conftest.py - OTA 升级测试的局部 fixtures
提供 ADB 驱动、OTA 测试配置等夹具
"""
from __future__ import annotations

import pytest

from common.config.config_manager import ConfigManager
from common.utils.logger import get_logger
from drivers.protocol_drivers.adb_driver import ADBDriver

logger = get_logger("fixtures.ota")


@pytest.fixture(scope="module")
def adb(config: ConfigManager) -> ADBDriver:
    """
    ADB 驱动 (module 级别共享)
    用于模拟 OTA 包推送、安装状态查询、版本信息获取等
    """
    env = config.get("env", "simulation")
    is_mock = env in ("simulation", "ci")

    driver = ADBDriver(
        serial=config.get("adb.serial", ""),
        host=config.get("adb.default_host", "127.0.0.1"),
        port=config.get("adb.default_port", 5037),
        mock=is_mock,
        command_timeout=config.get("adb.command_timeout", 30),
    )
    driver.connect()
    logger.info(f"ADB driver ready for OTA tests (mock={is_mock})")
    yield driver
    driver.disconnect()


@pytest.fixture(scope="module")
def ota_config(config: ConfigManager) -> dict:
    """OTA 升级测试配置参数"""
    return {
        # 超时
        "download_timeout_s": config.get("cockpit.ota.download_timeout", 600),
        "install_timeout_s": config.get("cockpit.ota.install_timeout", 1200),
        # OTA 包参数
        "package_sizes_mb": config.get(
            "cockpit.ota.package_sizes_mb", [50, 200, 500, 1024, 2048]
        ),
        "ota_server_url": config.get(
            "cockpit.ota.server_url", "https://ota.mock-server.com/v1"
        ),
        # 完整性校验
        "hash_algorithm": config.get("cockpit.ota.hash_algorithm", "sha256"),
        "signature_algorithm": config.get("cockpit.ota.signature_algorithm", "RSA-2048"),
        # 断点续传
        "resume_support": config.get("cockpit.ota.resume_support", True),
        # 下载重试
        "download_retries": config.get("cockpit.ota.download_retries", 3),
        # 最低电量要求
        "min_battery_percent": config.get("cockpit.ota.min_battery_percent", 30),
        # 最低存储空间要求 (MB)
        "min_storage_mb": config.get("cockpit.ota.min_storage_mb", 4096),
        # 网络类型
        "allowed_network_types": config.get(
            "cockpit.ota.allowed_network_types", ["wifi", "4g", "5g"]
        ),
    }