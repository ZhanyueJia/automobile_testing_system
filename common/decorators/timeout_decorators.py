"""
timeout - 超时控制装饰器
支持线程级超时(Windows 兼容）

注意: 由于 Python daemon 线程无法被强制终止，超时后后台线程仍可能
持有资源（如锁）。适用于测试场景的合理超时判定，勿用于安全关键的
永久资源场景。
"""
from __future__ import annotations

import functools
import threading
from typing import Any, Callable

from common.utils.logger import get_logger

logger = get_logger("timeout")


class TimeoutError(Exception):
    """操作超时异常"""
    pass


def timeout(seconds: float):
    """
    超时装饰器 - 使用线程实现 (跨平台)

    Args:
        seconds: 超时秒数

    注意: 超时后 daemon 线程继续运行直至进程退出，不占用文件描述符等关键资源。
          适用于测试超时检测，不适用于需要强制取消的场景。
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = [None]
            exception = [None]
            thread_done = threading.Event()

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e
                finally:
                    thread_done.set()

            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(timeout=seconds)

            if thread.is_alive():
                logger.warning(
                    f"[{func.__name__}] 超时 ({seconds}s)，"
                    f"后台线程将在进程退出时终止"
                )
                raise TimeoutError(
                    f"{func.__name__} 执行超过 {seconds} 秒超时"
                )

            if exception[0] is not None:
                raise exception[0]

            return result[0]

        return wrapper

    return decorator