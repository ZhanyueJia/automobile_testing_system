"""
log_call - 自动日志记录装饰器
记录函数入参、返回值、异常信息
"""
from __future__ import annotations

import functools
from typing import Any, Callable

from common.utils.logger import get_logger

logger = get_logger("call_trace")


def log_call(level: str = "DEBUG"):
    """
    自动记录函数调用的装饰器

    Args:
        level: 日志级别 (DEBUG / INFO / WARNING)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            func_name = func.__qualname__
            log_fn = getattr(logger, level.lower(), logger.debug)

            # 记录入参
            arg_str = ", ".join(
                [repr(a) for a in args[:5]]  # 最多记录 5 个位置参数
                + [f"{k}={v!r}" for k, v in list(kwargs.items())[:5]]
            )
            log_fn(f"→ {func_name}({arg_str})")

            try:
                result = func(*args, **kwargs)
                log_fn(f"← {func_name} => {result!r}"[:200])
                return result
            except Exception as e:
                logger.error(f"✗ {func_name} raised {type(e).__name__}: {e}")
                raise

        return wrapper

    return decorator