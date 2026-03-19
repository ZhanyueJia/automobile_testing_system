"""
retry - 重试装饰器
支持指数退避、自定义异常过滤、最大重试次数
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, Sequence, Type

from common.utils.logger import get_logger

logger = get_logger("retry")


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Sequence[Type[Exception]] = (Exception,),
    on_retry: Callable | None = None,
):
    """
    重试装饰器 - 支持指数退避

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟 (秒)
        backoff: 退避倍数
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数 (接收 attempt, exception 参数)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except tuple(exceptions) as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"[{func.__name__}] 第 {attempt}/{max_attempts} 次尝试失败: {e}, "
                            f"{current_delay:.1f}s 后重试"
                        )
                        if on_retry:
                            on_retry(attempt, e)
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"[{func.__name__}] 已达最大重试次数 {max_attempts}, 最后异常: {e}"
                        )

            if last_exception is not None:
                raise last_exception

        return wrapper

    return decorator