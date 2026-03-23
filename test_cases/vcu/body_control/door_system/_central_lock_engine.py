"""
Central Lock Engine - 中控锁测试引擎

提供中控锁测试的核心数据模型和测试引擎逻辑
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from common.utils.logger import get_logger
from common.utils.time_utils import TimeUtils
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver, CANMessage

logger = get_logger("test.central_lock.engine")


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
    min_response_time_ms: float = field(default_factory=lambda: float("inf"))
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
