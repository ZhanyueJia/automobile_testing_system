"""
measure_performance - 性能监控装饰器
自动采集函数执行耗时，并记录到日志
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable

from common.utils.logger import get_logger

logger = get_logger("performance")


def measure_performance(threshold_ms: float | None = None):
    """
    性能监控装饰器

    Args:
        threshold_ms: 可选的耗时阈值 (毫秒)，超过时记录 WARNING
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                msg = f"[{func.__name__}] 耗时: {elapsed_ms:.2f} ms"
                if threshold_ms and elapsed_ms > threshold_ms:
                    logger.warning(f"{msg} (超过阈值 {threshold_ms:.0f} ms)")
                else:
                    logger.debug(msg)

        return wrapper

    return decorator