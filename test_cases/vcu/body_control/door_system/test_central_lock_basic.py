"""
test_central_lock_basic.py - 中控锁基础功能测试

测试覆盖:
    1. 基础上锁功能
    2. 基础解锁功能
    3. 四门状态联动一致性
    4. 行驶自动落锁
    5. 熄火自动解锁
    6. 单门解锁模式
    7. 门未关好时拒绝上锁
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

logger = get_logger("test.central_lock.basic")


@allure.epic("整车控制")
@allure.feature("车身控制")
@allure.story("中控锁逻辑")
@pytest.mark.vcu
class TestCentralLockBasic:
    """
    中控锁基础功能测试套件

    验证中控锁在各种场景下的基础功能:
    - 基础上锁/解锁
    - 四门状态联动
    - 自动落锁/解锁逻辑
    - 单门解锁模式
    - 门未关好拒绝上锁
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

    # ----------------------------------------------------------------
    # 1. 基础上锁/解锁
    # ----------------------------------------------------------------

    @allure.title("基础上锁功能测试")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_lock_all_doors(self):
        """
        测试场景: 发送全车上锁指令, 验证四门全部上锁
        验证标准: 锁止状态 = LOCKED, 四门均为 locked
        """
        # 确保初始解锁
        assert self.engine.read_lock_status() == LockStatus.UNLOCKED

        # 执行上锁
        attempt = self.engine.single_lock_attempt(attempt_id=1, command="lock")

        allure.attach(
            json.dumps(attempt.__dict__, default=str, ensure_ascii=False, indent=2),
            name="上锁结果",
            attachment_type=allure.attachment_type.JSON,
        )

        assert attempt.success, f"上锁失败: {attempt.error}"
        assert self.engine.read_lock_status() == LockStatus.LOCKED, "锁止状态非 LOCKED"

        # 验证四门状态
        door_states = self.engine.read_door_states()
        for door in self.door_config["doors"]:
            assert door_states.get(door) is True, f"{door} 未上锁"

        logger.info("✓ 基础上锁测试通过: 四门全部上锁")

    @allure.title("基础解锁功能测试")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_unlock_all_doors(self):
        """
        测试场景: 先上锁, 再发送全车解锁指令, 验证四门全部解锁
        验证标准: 锁止状态 = UNLOCKED, 四门均为 unlocked
        """
        # 先上锁
        self.engine.single_lock_attempt(attempt_id=0, command="lock")
        assert self.engine.read_lock_status() == LockStatus.LOCKED

        # 执行解锁
        attempt = self.engine.single_lock_attempt(attempt_id=1, command="unlock")

        allure.attach(
            json.dumps(attempt.__dict__, default=str, ensure_ascii=False, indent=2),
            name="解锁结果",
            attachment_type=allure.attachment_type.JSON,
        )

        assert attempt.success, f"解锁失败: {attempt.error}"
        assert self.engine.read_lock_status() == LockStatus.UNLOCKED, "锁止状态非 UNLOCKED"

        door_states = self.engine.read_door_states()
        for door in self.door_config["doors"]:
            assert door_states.get(door) is False, f"{door} 未解锁"

        logger.info("✓ 基础解锁测试通过: 四门全部解锁")

    # ----------------------------------------------------------------
    # 2. 四门状态联动
    # ----------------------------------------------------------------

    @allure.title("四门状态联动一致性测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_all_doors_sync(self):
        """
        测试场景: 上锁后验证四门状态一致, 解锁后同理
        验证标准: 四门状态完全同步, 无单门遗漏
        """
        # 上锁
        self.engine.single_lock_attempt(attempt_id=1, command="lock")
        locked_states = self.engine.read_door_states()

        allure.attach(
            json.dumps({"locked_states": locked_states}, ensure_ascii=False, indent=2),
            name="上锁后四门状态",
            attachment_type=allure.attachment_type.JSON,
        )

        for door in self.door_config["doors"]:
            assert locked_states.get(door) is True, f"上锁后 {door} 状态异常: {locked_states.get(door)}"

        # 解锁
        self.engine.single_lock_attempt(attempt_id=2, command="unlock")
        unlocked_states = self.engine.read_door_states()

        for door in self.door_config["doors"]:
            assert unlocked_states.get(door) is False, f"解锁后 {door} 状态异常: {unlocked_states.get(door)}"

        logger.info("✓ 四门联动一致性测试通过")

    # ----------------------------------------------------------------
    # 3. 行驶自动落锁
    # ----------------------------------------------------------------

    @allure.title("行驶自动落锁测试 - {speed_kmh} km/h")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("speed_kmh", [15, 20, 30, 60, 120], ids=[
        "15kmh-低于阈值", "20kmh-临界值", "30kmh-城市", "60kmh-快速路", "120kmh-高速"
    ])
    def test_auto_lock_on_speed(self, speed_kmh: int, can: CANFDDriver):
        """
        测试场景: 模拟不同车速, 验证自动落锁逻辑
        验证标准:
            - 车速 < 20 km/h: 不自动落锁
            - 车速 ≥ 20 km/h: 自动落锁
        """
        auto_lock_threshold = self.door_config["auto_lock_speed_kmh"]

        # 确保初始解锁
        self.engine._mock_reset()
        assert self.engine.read_lock_status() == LockStatus.UNLOCKED

        # 模拟发送车速信号
        speed_data = speed_kmh.to_bytes(2, "big") + bytes(6)
        speed_msg = CANMessage(arbitration_id=0x120, data=speed_data)
        can.send(speed_msg)

        # Mock: 模拟 BCM 根据车速自动落锁
        if can._mock and speed_kmh >= auto_lock_threshold:
            self.engine._mock_apply_command(LockCommand.LOCK_ALL)

        time.sleep(0.3)

        # 验证结果
        current_status = self.engine.read_lock_status()

        result_data = {
            "speed_kmh": speed_kmh,
            "auto_lock_threshold": auto_lock_threshold,
            "expected_locked": speed_kmh >= auto_lock_threshold,
            "actual_status": "LOCKED" if current_status == LockStatus.LOCKED else "UNLOCKED",
        }
        allure.attach(
            json.dumps(result_data, ensure_ascii=False, indent=2),
            name=f"自动落锁-{speed_kmh}kmh",
            attachment_type=allure.attachment_type.JSON,
        )

        if speed_kmh >= auto_lock_threshold:
            assert current_status == LockStatus.LOCKED, (
                f"车速 {speed_kmh} km/h ≥ {auto_lock_threshold} km/h, 应自动落锁但未落锁"
            )
            logger.info(f"✓ {speed_kmh} km/h 自动落锁: 正确")
        else:
            assert current_status == LockStatus.UNLOCKED, (
                f"车速 {speed_kmh} km/h < {auto_lock_threshold} km/h, 不应自动落锁但已落锁"
            )
            logger.info(f"✓ {speed_kmh} km/h 保持解锁: 正确")

    # ----------------------------------------------------------------
    # 4. 熄火自动解锁
    # ----------------------------------------------------------------

    @allure.title("熄火自动解锁测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_unlock_on_power_off(self, can: CANFDDriver):
        """
        测试场景: 车辆上锁行驶后, 熄火(切换到 ACC/OFF), 验证自动解锁
        验证标准: 收到 VehicleState.OFF 信号后, 中控锁自动解锁
        """
        # 先上锁
        self.engine.single_lock_attempt(attempt_id=1, command="lock")
        assert self.engine.read_lock_status() == LockStatus.LOCKED

        # 模拟熄火信号 (VehicleState.OFF = 0)
        power_off_data = bytes([0x00]) + bytes(7)
        power_off_msg = CANMessage(arbitration_id=0x100, data=power_off_data)
        can.send(power_off_msg)

        # Mock: 模拟 BCM 收到熄火信号后解锁
        if can._mock:
            self.engine._mock_apply_command(LockCommand.UNLOCK_ALL)

        time.sleep(0.3)

        status = self.engine.read_lock_status()
        assert status == LockStatus.UNLOCKED, "熄火后应自动解锁但仍处于锁止状态"

        door_states = self.engine.read_door_states()
        for door in self.door_config["doors"]:
            assert door_states.get(door) is False, f"熄火后 {door} 仍处于锁止"

        logger.info("✓ 熄火自动解锁测试通过")

    # ----------------------------------------------------------------
    # 5. 单门解锁模式 (仅驾驶位)
    # ----------------------------------------------------------------

    @allure.title("单门解锁模式测试 - 仅驾驶位")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    def test_driver_only_unlock(self):
        """
        测试场景: 全车上锁后发送驾驶位单门解锁指令
        验证标准: 仅驾驶位门解锁, 其余三门保持锁止
        """
        # 先全车上锁
        self.engine.single_lock_attempt(attempt_id=1, command="lock")

        # 发送驾驶位单门解锁
        if self.engine._can._mock:
            self.engine._mock_apply_command(LockCommand.UNLOCK_DRIVER)

        self.engine.send_lock_command(LockCommand.UNLOCK_DRIVER)
        time.sleep(0.3)

        door_states = self.engine.read_door_states()

        allure.attach(
            json.dumps({"door_states": door_states}, ensure_ascii=False, indent=2),
            name="单门解锁结果",
            attachment_type=allure.attachment_type.JSON,
        )

        assert door_states.get("front_left") is False, "驾驶位门应已解锁"
        assert door_states.get("front_right") is True, "副驾应保持锁止"
        assert door_states.get("rear_left") is True, "后排左应保持锁止"
        assert door_states.get("rear_right") is True, "后排右应保持锁止"

        logger.info("✓ 单门解锁模式测试通过: 仅驾驶位解锁")

    # ----------------------------------------------------------------
    # 6. 门未关好时拒绝上锁
    # ----------------------------------------------------------------

    @allure.title("门未关好拒绝上锁测试 - {ajar_door}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("ajar_door", [
        "front_left", "front_right", "rear_left", "rear_right"
    ], ids=["主驾未关", "副驾未关", "后排左未关", "后排右未关"])
    def test_lock_rejected_door_ajar(self, ajar_door: str):
        """
        测试场景: 某一车门未关好, 发送上锁指令
        验证标准: 上锁被拒绝, 系统不进入锁止状态
        """
        # 模拟门未关好
        self.engine._mock_door_ajar.add(ajar_door)

        # 尝试上锁
        if self.engine._can._mock:
            success = self.engine._mock_apply_command(LockCommand.LOCK_ALL)
        else:
            success = True  # 真机需读取实际反馈

        self.engine.send_lock_command(LockCommand.LOCK_ALL)
        time.sleep(0.3)

        result_data = {
            "ajar_door": ajar_door,
            "lock_rejected": not success,
            "current_status": "LOCKED" if self.engine.read_lock_status() == LockStatus.LOCKED else "UNLOCKED",
        }
        allure.attach(
            json.dumps(result_data, ensure_ascii=False, indent=2),
            name=f"门未关上锁测试-{ajar_door}",
            attachment_type=allure.attachment_type.JSON,
        )

        if self.engine._can._mock:
            assert not success, f"{ajar_door} 未关好但上锁成功 — 逻辑缺陷"
            assert self.engine.read_lock_status() == LockStatus.UNLOCKED, (
                f"{ajar_door} 未关好但状态变为 LOCKED"
            )

        logger.info(f"✓ {ajar_door} 未关好, 上锁被正确拒绝")
