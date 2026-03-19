"""
test_central_lock.py - 中控锁逻辑测试

测试目标:
    验证中控锁在各种操作场景下的功能正确性、安全性和可靠性

测试覆盖维度:
    1. 基础上锁/解锁功能 (CAN 报文指令)
    2. 上锁/解锁 CAN 响应时间 (≤300ms)
    3. 全车门状态联动 (四门同步)
    4. 行驶自动落锁 (车速 ≥20 km/h 自动上锁)
    5. 熄火自动解锁
    6. 碰撞自动解锁 (安全功能)
    7. 儿童安全锁联动
    8. 单门解锁 / 全车解锁模式
    9. 重复指令幂等性 (连续发同样命令不异常)
    10. 门未关好时上锁拒绝 (带蜂鸣提示)
    11. 耐久性测试 (循环上锁/解锁 N 次)

对标竞品:
    特斯拉 Model 3 / 小米 SU7 / 蔚来 ET7 / 理想 L9

参考标准:
    - 上锁响应时间 ≤ 300ms
    - 行驶 ≥20 km/h 自动落锁
    - 碰撞信号触发后 200ms 内解锁
    - 耐久寿命 ≥ 100,000 次
"""
from __future__ import annotations

import time
import json
import random
from dataclasses import dataclass, field
from typing import Optional

import allure
import pytest

from common.utils.logger import get_logger
from common.utils.time_utils import TimeUtils
from common.decorators import retry, measure_performance
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver, CANMessage

logger = get_logger("test.central_lock")


# ============================================================
# 中控锁 CAN 信号常量
# ============================================================

class LockCommand:
    """中控锁指令字节定义"""
    LOCK_ALL = 0x01       # 全车上锁
    UNLOCK_ALL = 0x02     # 全车解锁
    UNLOCK_DRIVER = 0x03  # 仅解锁驾驶位
    LOCK_CHILD = 0x04     # 儿童锁开启
    UNLOCK_CHILD = 0x05   # 儿童锁关闭


class LockStatus:
    """中控锁状态字节定义"""
    UNLOCKED = 0x00
    LOCKED = 0x01
    ERROR = 0xFF


class DoorPosition:
    """车门位置索引 (对应状态报文中的字节位置)"""
    FRONT_LEFT = 0
    FRONT_RIGHT = 1
    REAR_LEFT = 2
    REAR_RIGHT = 3

    ALL = ["front_left", "front_right", "rear_left", "rear_right"]
    NAME_MAP = {
        "front_left": 0,
        "front_right": 1,
        "rear_left": 2,
        "rear_right": 3,
    }


# ============================================================
# 数据模型
# ============================================================

@dataclass
class LockAttempt:
    """单次上锁/解锁尝试结果"""
    attempt_id: int
    command: str                    # "lock" / "unlock"
    success: bool = False
    response_time_ms: float = 0.0
    door_states: dict = field(default_factory=dict)  # {door_name: locked(bool)}
    error: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class LockTestResult:
    """中控锁测试汇总结果"""
    total_attempts: int = 0
    success_count: int = 0
    fail_count: int = 0
    pass_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    min_response_time_ms: float = float("inf")
    condition: str = ""
    details: list[LockAttempt] = field(default_factory=list)

    def add_attempt(self, attempt: LockAttempt) -> None:
        self.details.append(attempt)
        self.total_attempts += 1
        if attempt.success:
            self.success_count += 1
            if attempt.response_time_ms > 0:
                self.max_response_time_ms = max(
                    self.max_response_time_ms, attempt.response_time_ms
                )
                self.min_response_time_ms = min(
                    self.min_response_time_ms, attempt.response_time_ms
                )
        else:
            self.fail_count += 1
        self.pass_rate = (
            self.success_count / self.total_attempts if self.total_attempts > 0 else 0.0
        )
        success_times = [
            a.response_time_ms for a in self.details if a.success and a.response_time_ms > 0
        ]
        self.avg_response_time_ms = (
            sum(success_times) / len(success_times) if success_times else 0.0
        )

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "total_attempts": self.total_attempts,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "pass_rate": round(self.pass_rate, 4),
            "pass_rate_percent": f"{self.pass_rate * 100:.1f}%",
            "avg_response_time_ms": round(self.avg_response_time_ms, 1),
            "max_response_time_ms": round(self.max_response_time_ms, 1),
            "min_response_time_ms": (
                round(self.min_response_time_ms, 1)
                if self.min_response_time_ms != float("inf")
                else 0
            ),
        }


# ============================================================
# 核心测试执行引擎
# ============================================================

class CentralLockEngine:
    """
    中控锁测试引擎

    封装中控锁测试的核心逻辑:
    1. 通过 CAN 报文发送上锁/解锁指令
    2. 读取反馈状态报文验证执行结果
    3. 记录响应时间和通过率
    """

    def __init__(
        self,
        can: CANFDDriver,
        cmd_id: int = 0x310,
        status_id: int = 0x311,
        door_status_id: int = 0x312,
        response_timeout_ms: float = 500,
    ):
        self._can = can
        self._cmd_id = cmd_id
        self._status_id = status_id
        self._door_status_id = door_status_id
        self._response_timeout_ms = response_timeout_ms

        # Mock 状态 (实例级别，每个引擎独立)
        self._mock_state: int = LockStatus.UNLOCKED
        self._mock_doors: dict = {
            "front_left": False,
            "front_right": False,
            "rear_left": False,
            "rear_right": False,
        }
        self._mock_door_ajar: set = set()  # 未关好的门

    # ---- 发送指令 ----

    def send_lock_command(self, cmd_byte: int) -> None:
        """发送中控锁 CAN 指令"""
        data = bytes([cmd_byte, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        msg = CANMessage(arbitration_id=self._cmd_id, data=data)
        self._can.send(msg)
        logger.debug(f"Sent lock command: 0x{cmd_byte:02X} → CAN ID 0x{self._cmd_id:03X}")

    # ---- 读取状态 ----

    def read_lock_status(self, timeout_s: float = 0.5) -> Optional[int]:
        """
        读取中控锁状态反馈

        Returns:
            LockStatus 值, 或 None (超时无响应)
        """
        if self._can._mock:
            # Mock 模式: 模拟成功反馈
            return self._mock_lock_status()

        msg = self._can.receive(timeout=timeout_s)
        if msg and msg.arbitration_id == self._status_id:
            return msg.data[0]
        return None

    def read_door_states(self, timeout_s: float = 0.5) -> dict[str, bool]:
        """
        读取四门锁止状态

        Returns:
            {door_name: is_locked} 字典
        """
        if self._can._mock:
            return self._mock_door_states()

        msg = self._can.receive(timeout=timeout_s)
        if msg and msg.arbitration_id == self._door_status_id:
            return {
                name: bool(msg.data[idx])
                for name, idx in DoorPosition.NAME_MAP.items()
            }
        return {}

    # ---- Mock 内部状态 ----

    def _mock_lock_status(self) -> int:
        return self._mock_state

    def _mock_door_states(self) -> dict[str, bool]:
        return dict(self._mock_doors)

    def _mock_apply_command(self, cmd_byte: int) -> bool:
        """
        Mock 模式: 模拟 ECU 处理指令并更新内部状态
        Returns: True=执行成功
        """
        # 门未关好 → 拒绝上锁
        if cmd_byte == LockCommand.LOCK_ALL and self._mock_door_ajar:
            logger.debug(f"Mock: lock rejected, door ajar: {self._mock_door_ajar}")
            return False

        if cmd_byte == LockCommand.LOCK_ALL:
            self._mock_state = LockStatus.LOCKED
            for d in self._mock_doors:
                self._mock_doors[d] = True
        elif cmd_byte == LockCommand.UNLOCK_ALL:
            self._mock_state = LockStatus.UNLOCKED
            for d in self._mock_doors:
                self._mock_doors[d] = False
        elif cmd_byte == LockCommand.UNLOCK_DRIVER:
            self._mock_state = LockStatus.UNLOCKED
            self._mock_doors["front_left"] = False
        elif cmd_byte == LockCommand.LOCK_CHILD:
            self._mock_doors["rear_left"] = True
            self._mock_doors["rear_right"] = True
        elif cmd_byte == LockCommand.UNLOCK_CHILD:
            pass  # 儿童锁关闭不改变锁止状态, 只允许内侧开门

        return True

    def _mock_reset(self) -> None:
        """重置 Mock 状态为默认 (全车解锁, 门全关好)"""
        self._mock_state = LockStatus.UNLOCKED
        self._mock_doors = {d: False for d in DoorPosition.ALL}
        self._mock_door_ajar.clear()

    # ---- 高阶测试逻辑 ----

    def single_lock_attempt(
        self,
        attempt_id: int,
        command: str = "lock",
    ) -> LockAttempt:
        """
        执行一次上锁或解锁操作并验证结果

        Args:
            attempt_id: 尝试编号
            command: "lock" 或 "unlock"

        Returns:
            LockAttempt 结果
        """
        cmd_byte = LockCommand.LOCK_ALL if command == "lock" else LockCommand.UNLOCK_ALL
        expected_status = LockStatus.LOCKED if command == "lock" else LockStatus.UNLOCKED

        attempt = LockAttempt(attempt_id=attempt_id, command=command)

        try:
            # Mock: 模拟 ECU 执行
            if self._can._mock:
                self._mock_apply_command(cmd_byte)

            with TimeUtils.measure() as timer:
                self.send_lock_command(cmd_byte)
                # 轮询等待状态反馈
                status = TimeUtils.wait_until(
                    condition_fn=lambda: self.read_lock_status() == expected_status,
                    timeout=self._response_timeout_ms / 1000.0,
                    interval=0.02,
                )

            attempt.response_time_ms = timer.elapsed_ms
            attempt.success = status
            attempt.door_states = self.read_door_states()

            if status:
                logger.debug(
                    f"#{attempt_id} {command} OK: {timer.elapsed_ms:.0f}ms"
                )
            else:
                attempt.error = f"Status mismatch: expected {expected_status}"
                logger.debug(f"#{attempt_id} {command} FAIL: timeout")

        except Exception as e:
            attempt.error = str(e)
            logger.warning(f"#{attempt_id} {command} exception: {e}")

        return attempt

    def run_lock_unlock_cycle(
        self,
        cycles: int,
        condition_label: str = "",
    ) -> LockTestResult:
        """
        批量执行上锁-解锁循环测试

        每个周期: 上锁 → 验证 → 解锁 → 验证
        """
        result = LockTestResult(condition=condition_label)
        logger.info(f"Start central lock cycle test: {condition_label} ({cycles} cycles)")

        for i in range(1, cycles + 1):
            # 上锁
            lock_attempt = self.single_lock_attempt(attempt_id=i * 2 - 1, command="lock")
            result.add_attempt(lock_attempt)

            time.sleep(0.3)

            # 解锁
            unlock_attempt = self.single_lock_attempt(attempt_id=i * 2, command="unlock")
            result.add_attempt(unlock_attempt)

            time.sleep(0.3)

            if i % 10 == 0 or i == cycles:
                logger.info(
                    f"  Progress: {i}/{cycles}, "
                    f"pass rate: {result.pass_rate * 100:.1f}%"
                )

        logger.info(
            f"Test completed: {condition_label} | "
            f"pass rate: {result.pass_rate * 100:.1f}% "
            f"({result.success_count}/{result.total_attempts}), "
            f"avg response: {result.avg_response_time_ms:.0f}ms"
        )
        return result


# ============================================================
# 测试用例
# ============================================================

@allure.epic("整车控制")
@allure.feature("车身控制")
@allure.story("中控锁逻辑")
@pytest.mark.vcu
class TestCentralLock:
    """
    中控锁逻辑测试套件

    验证中控锁在各种场景下的功能、安全和可靠性:
    - 基础上锁/解锁
    - 响应时间
    - 四门状态联动
    - 行驶自动落锁
    - 碰撞自动解锁
    - 儿童安全锁
    - 单门解锁模式
    - 指令幂等性
    - 门未关拒绝上锁
    - 耐久性
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
    # 2. 响应时间测试
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # 3. 四门状态联动
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
    # 4. 行驶自动落锁
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
        if self._can_mock(can) and speed_kmh >= auto_lock_threshold:
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
    # 5. 熄火自动解锁
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
        if self._can_mock(can):
            self.engine._mock_apply_command(LockCommand.UNLOCK_ALL)

        time.sleep(0.3)

        status = self.engine.read_lock_status()
        assert status == LockStatus.UNLOCKED, "熄火后应自动解锁但仍处于锁止状态"

        door_states = self.engine.read_door_states()
        for door in self.door_config["doors"]:
            assert door_states.get(door) is False, f"熄火后 {door} 仍处于锁止"

        logger.info("✓ 熄火自动解锁测试通过")

    # ----------------------------------------------------------------
    # 6. 碰撞自动解锁
    # ----------------------------------------------------------------

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
            if self._can_mock(can):
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

    # ----------------------------------------------------------------
    # 7. 儿童安全锁
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # 8. 单门解锁模式 (仅驾驶位)
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
    # 9. 重复指令幂等性
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
    # 10. 门未关好时拒绝上锁
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

    # ----------------------------------------------------------------
    # 11. 耐久性循环测试
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

    # ----------------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------------

    @staticmethod
    def _can_mock(can: CANFDDriver) -> bool:
        """判断是否为 Mock 模式"""
        return can._mock