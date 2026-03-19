"""
conftest.py - 感知系统测试的局部 fixtures
提供 CAN-FD 驱动、感知系统配置等夹具
"""
from __future__ import annotations

import pytest

from common.config.config_manager import ConfigManager
from common.utils.logger import get_logger
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver

logger = get_logger("fixtures.perception")


@pytest.fixture(scope="module")
def can(config: ConfigManager) -> CANFDDriver:
    """
    CAN-FD 驱动 (module 级别共享)
    用于接收感知目标列表、传感器状态等 CAN 报文
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
    logger.info(f"CAN-FD driver ready for perception tests (mock={is_mock})")
    yield driver
    driver.disconnect()


@pytest.fixture(scope="module")
def perception_config(config: ConfigManager) -> dict:
    """感知系统测试配置参数"""
    return {
        # 检测精度阈值
        "detection_accuracy_min": config.get(
            "adas.perception.detection_accuracy_min", 0.95
        ),
        # 检测延迟上限 (ms)
        "detection_latency_max_ms": config.get(
            "adas.perception.detection_latency_max_ms", 50
        ),
        # 检测距离范围 (m)
        "detection_range_m": config.get(
            "adas.perception.detection_range_m", 200
        ),
        # 测试目标类型
        "target_types": config.get(
            "adas.perception.target_types",
            ["vehicle", "pedestrian", "cyclist", "truck", "traffic_sign", "traffic_light"],
        ),
        # 测试轮次
        "test_rounds": config.get(
            "adas.perception.test_rounds", 100
        ),
        # 摄像头分辨率
        "camera_resolution": config.get(
            "adas.perception.camera_resolution", "1920x1080"
        ),
        # 帧率
        "camera_fps": config.get(
            "adas.perception.camera_fps", 30
        ),
        # CAN ID
        "camera_target_list_id": config.get(
            "adas.perception.camera_target_list_id", 0x500
        ),
        "camera_status_id": config.get(
            "adas.perception.camera_status_id", 0x501
        ),
        # 传感器数量 (从车型配置获取)
        "camera_count": config.get(
            "current_vehicle.adas.sensors.camera_count", 6
        ),
        # 测试距离 (m)
        "test_distances_m": config.get(
            "adas.perception.test_distances_m", [10, 30, 50, 80, 120, 200]
        ),
        # IoU 阈值 (目标框重叠度)
        "iou_threshold": config.get(
            "adas.perception.iou_threshold", 0.5
        ),
    }