"""
TimeUtils - 时间处理工具
精确计时、超时判定、时间戳转换
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class TimingResult:
    """计时结果"""
    elapsed_ms: float = 0.0
    elapsed_s: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0


class TimeUtils:
    """时间工具集"""

    @staticmethod
    @contextmanager
    def measure() -> Generator[TimingResult, None, None]:
        """
        上下文管理器 - 精确测量代码段耗时

        Usage:
            with TimeUtils.measure() as t:
                do_something()
            print(f"耗时: {t.elapsed_ms:.2f} ms")
        """
        result = TimingResult()
        result.started_at = time.perf_counter()
        try:
            yield result
        finally:
            result.ended_at = time.perf_counter()
            result.elapsed_s = result.ended_at - result.started_at
            result.elapsed_ms = result.elapsed_s * 1000.0

    @staticmethod
    def wait(seconds: float) -> None:
        """等待指定秒数"""
        time.sleep(seconds)

    @staticmethod
    def wait_until(condition_fn, timeout: float = 10.0, interval: float = 0.5) -> bool:
        """
        轮询等待条件满足

        Args:
            condition_fn: 条件函数，返回 True 表示条件满足
            timeout: 超时时间 (秒)
            interval: 轮询间隔 (秒)

        Returns:
            是否在超时前满足条件
        """
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if condition_fn():
                return True
            time.sleep(interval)
        return False

    @staticmethod
    def timestamp_ms() -> int:
        """当前时间戳 (毫秒)"""
        return int(time.time() * 1000)