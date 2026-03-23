"""
test_central_lock_durability.py - 中控锁耐久性和幂等性测试

测试覆盖:
    1. 重复上锁指令幂等性测试
    2. 重复解锁指令幂等性测试
    3. 耐久性循环测试
"""
from __future__ import annotations

import json

import allure
import pytest

from common.utils.logger import get_logger
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver
from test_cases.vcu.body_control.door_system._central_lock_engine import (
    CentralLockEngine,
    LockStatus,
)

logger = get_logger("test.central_lock.durability")


@allure.epic("整车控制")
@allure.feature("车身控制")
@allure.story("中控锁耐久性")
@pytest.mark.vcu
class TestCentralLockDurability:
    """
    中控锁耐久性和幂等性测试套件

    验证中控锁在重复操作和长时间运行下的稳定性:
    - 指令幂等性
    - 循环耐久性
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

        # 每个用例前重置 Mock 状态
        self.engine._mock_reset()

    # ----------------------------------------------------------------
    # 1. 重复指令幂等性
    # ----------------------------------------------------------------

    @allure.title("重复上锁指令幂等性测试")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    def test_lock_idempotency(self):
        """
        测试场景: 已上锁状态下连续发送上锁指令
        验证标准: 不产生异常, 状态保持 LOCKED
        """
        # 先上锁
        self.engine.single_lock_attempt(attempt_id=0, command="lock")
        assert self.engine.read_lock_status() == LockStatus.LOCKED

        # 连续发送 5 次上锁
        for i in range(1, 6):
            attempt = self.engine.single_lock_attempt(attempt_id=i, command="lock")
            assert attempt.success, f"第 {i} 次重复上锁失败: {attempt.error}"
            assert self.engine.read_lock_status() == LockStatus.LOCKED, (
                f"第 {i} 次重复上锁后状态异常"
            )

        logger.info("✓ 上锁幂等性测试通过: 5 次重复指令均正常")

    @allure.title("重复解锁指令幂等性测试")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    def test_unlock_idempotency(self):
        """
        测试场景: 已解锁状态下连续发送解锁指令
        验证标准: 不产生异常, 状态保持 UNLOCKED
        """
        assert self.engine.read_lock_status() == LockStatus.UNLOCKED

        for i in range(1, 6):
            attempt = self.engine.single_lock_attempt(attempt_id=i, command="unlock")
            assert attempt.success, f"第 {i} 次重复解锁失败: {attempt.error}"
            assert self.engine.read_lock_status() == LockStatus.UNLOCKED

        logger.info("✓ 解锁幂等性测试通过: 5 次重复指令均正常")

    # ----------------------------------------------------------------
    # 2. 耐久性循环测试
    # ----------------------------------------------------------------

    @allure.title("中控锁耐久性循环测试")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    @pytest.mark.regression
    def test_lock_unlock_endurance(self):
        """
        测试场景: 反复上锁/解锁 N 次, 验证系统稳定性
        验证标准:
            - 成功率 ≥ 99%
            - 无累积性故障
        """
        cycles = min(self.door_config["test_cycles"], 30)

        result = self.engine.run_lock_unlock_cycle(
            cycles=cycles,
            condition_label=f"endurance-{cycles}-cycles",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="耐久性测试结果",
            attachment_type=allure.attachment_type.JSON,
        )

        min_pass_rate = 0.99
        assert result.pass_rate >= min_pass_rate, (
            f"耐久测试通过率 {result.pass_rate * 100:.1f}% "
            f"未达标 (要求 ≥ {min_pass_rate * 100:.0f}%), "
            f"成功 {result.success_count}/{result.total_attempts}"
        )

        logger.info(
            f"✓ 耐久性测试通过: {result.pass_rate * 100:.1f}% "
            f"({cycles} 上下锁循环, "
            f"avg {result.avg_response_time_ms:.0f}ms)"
        )
