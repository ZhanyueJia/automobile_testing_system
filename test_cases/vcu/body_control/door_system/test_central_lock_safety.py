"""
test_central_lock_safety.py - 中控锁安全功能测试

测试覆盖:
    1. 碰撞自动解锁安全测试
    2. 儿童安全锁启用测试
"""
from __future__ import annotations

import json
import time

import allure
import pytest

from common.utils.logger import get_logger
from common.utils.time_utils import TimeUtils
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver, CANMessage
from test_cases.vcu.body_control.door_system._central_lock_engine import (
    CentralLockEngine,
    LockCommand,
    LockStatus,
)

logger = get_logger("test.central_lock.safety")


@allure.epic("整车控制")
@allure.feature("车身控制")
@allure.story("中控锁安全功能")
@pytest.mark.vcu
class TestCentralLockSafety:
    """
    中控锁安全功能测试套件

    验证中控锁的安全相关功能:
    - 碰撞自动解锁
    - 儿童安全锁
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

    @allure.title("碰撞自动解锁安全测试")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.safety
    def test_crash_auto_unlock(self, can: CANFDDriver):
        """
        测试场景: 车辆上锁状态下收到碰撞信号, 验证自动解锁
        验证标准:
            - 碰撞信号触发后自动解锁
            - 属于安全关键功能
        """
        # 先上锁
        self.engine.single_lock_attempt(attempt_id=1, command="lock")
        assert self.engine.read_lock_status() == LockStatus.LOCKED

        # 模拟碰撞气囊触发信号
        crash_signal = bytes([0x01]) + bytes(7)  # byte[0]=1 表示碰撞触发
        crash_msg = CANMessage(arbitration_id=0x1A0, data=crash_signal)

        with TimeUtils.measure() as timer:
            can.send(crash_msg)

            # Mock: 碰撞触发自动解锁
            if can._mock:
                self.engine._mock_apply_command(LockCommand.UNLOCK_ALL)

            # 等待解锁
            unlocked = TimeUtils.wait_until(
                condition_fn=lambda: self.engine.read_lock_status() == LockStatus.UNLOCKED,
                timeout=0.5,
                interval=0.02,
            )

        result_data = {
            "crash_signal_sent": True,
            "unlocked": unlocked,
            "response_time_ms": round(timer.elapsed_ms, 1),
        }
        allure.attach(
            json.dumps(result_data, ensure_ascii=False, indent=2),
            name="碰撞自动解锁结果",
            attachment_type=allure.attachment_type.JSON,
        )

        assert unlocked, "碰撞信号触发后未自动解锁 — 安全缺陷!"
        logger.info(f"✓ 碰撞自动解锁通过: {timer.elapsed_ms:.0f}ms")

    @allure.title("儿童安全锁启用测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_child_lock_enable(self):
        """
        测试场景: 启用儿童锁, 验证后排门锁状态
        验证标准: 后排左右车门进入锁止状态
        """
        self.engine._mock_reset()

        # 发送儿童锁启用指令
        if self.engine._can._mock:
            self.engine._mock_apply_command(LockCommand.LOCK_CHILD)

        self.engine.send_lock_command(LockCommand.LOCK_CHILD)
        time.sleep(0.3)

        door_states = self.engine.read_door_states()

        allure.attach(
            json.dumps({"door_states": door_states}, ensure_ascii=False, indent=2),
            name="儿童锁启用后车门状态",
            attachment_type=allure.attachment_type.JSON,
        )

        assert door_states.get("rear_left") is True, "后排左门未锁止"
        assert door_states.get("rear_right") is True, "后排右门未锁止"
        # 前排应不受影响
        assert door_states.get("front_left") is False, "前排左门被意外锁止"
        assert door_states.get("front_right") is False, "前排右门被意外锁止"

        logger.info("✓ 儿童安全锁测试通过: 后排锁止, 前排正常")
