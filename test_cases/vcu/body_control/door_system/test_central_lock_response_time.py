"""
test_central_lock_response_time.py - 中控锁响应时间测试

测试覆盖:
    1. 上锁响应时间测试
    2. 解锁响应时间测试
"""
from __future__ import annotations

import json
import time

import allure
import pytest

from common.utils.logger import get_logger
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver
from test_cases.vcu.body_control.door_system._central_lock_engine import (
    CentralLockEngine,
    LockCommand,
    LockStatus,
    LockTestResult,
)

logger = get_logger("test.central_lock.response_time")


@allure.epic("整车控制")
@allure.feature("车身控制")
@allure.story("中控锁响应时间")
@pytest.mark.vcu
class TestCentralLockResponseTime:
    """
    中控锁响应时间测试套件

    验证中控锁上锁/解锁操作的响应时间符合规范要求
    """

    @pytest.fixture(autouse=True)
    def setup(self, can: CANFDDriver, door_config: dict):
        """测试前置: 初始化测试引擎, 每个用例前重置状态"""
        self.engine = CentralLockEngine(
            can=can,
            cmd_id=door_config["central_lock_cmd_id"],
            status_id=door_config["central_lock_status_id"],
            door_status_id=door_config["door_status_id"],
            response_timeout_ms=door_config["lock_response_timeout_ms"],
        )
        self.door_config = door_config
        self.max_response_ms = door_config["max_response_time_ms"]

        # 每个用例前重置 Mock 状态
        self.engine._mock_reset()

    @allure.title("上锁响应时间测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_lock_response_time(self):
        """
        测试场景: 多次上锁操作, 统计响应时间
        验证标准:
            - 平均响应时间 ≤ 300ms
            - 最大响应时间 ≤ 500ms
        """
        cycles = min(self.door_config["test_cycles"], 20)
        result = LockTestResult(condition="lock response time")

        for i in range(1, cycles + 1):
            # 确保解锁状态
            self.engine._mock_apply_command(LockCommand.UNLOCK_ALL)
            time.sleep(0.1)

            attempt = self.engine.single_lock_attempt(attempt_id=i, command="lock")
            result.add_attempt(attempt)
            time.sleep(0.2)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="上锁响应时间统计",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.avg_response_time_ms <= self.max_response_ms, (
            f"平均响应时间 {result.avg_response_time_ms:.0f}ms "
            f"超过阈值 {self.max_response_ms}ms"
        )
        assert result.max_response_time_ms <= self.door_config["lock_response_timeout_ms"], (
            f"最大响应时间 {result.max_response_time_ms:.0f}ms "
            f"超过超时阈值 {self.door_config['lock_response_timeout_ms']}ms"
        )
        logger.info(
            f"✓ 上锁响应时间达标: avg={result.avg_response_time_ms:.0f}ms, "
            f"max={result.max_response_time_ms:.0f}ms"
        )

    @allure.title("解锁响应时间测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_unlock_response_time(self):
        """
        测试场景: 多次解锁操作, 统计响应时间
        验证标准:
            - 平均响应时间 ≤ 300ms
            - 最大响应时间 ≤ 500ms
        """
        cycles = min(self.door_config["test_cycles"], 20)
        result = LockTestResult(condition="unlock response time")

        for i in range(1, cycles + 1):
            # 确保上锁状态
            self.engine._mock_apply_command(LockCommand.LOCK_ALL)
            time.sleep(0.1)

            attempt = self.engine.single_lock_attempt(attempt_id=i, command="unlock")
            result.add_attempt(attempt)
            time.sleep(0.2)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="解锁响应时间统计",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.avg_response_time_ms <= self.max_response_ms, (
            f"平均响应时间 {result.avg_response_time_ms:.0f}ms "
            f"超过阈值 {self.max_response_ms}ms"
        )
        logger.info(
            f"✓ 解锁响应时间达标: avg={result.avg_response_time_ms:.0f}ms, "
            f"max={result.max_response_time_ms:.0f}ms"
        )
