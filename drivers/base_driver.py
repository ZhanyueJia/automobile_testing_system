"""
BaseDriver - 所有驱动的抽象基类
定义驱动生命周期: connect / disconnect / is_connected / reset
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from common.utils.logger import get_logger

logger = get_logger("driver.base")


class BaseDriver(ABC):
    """驱动抽象基类"""

    def __init__(self, name: str = "BaseDriver"):
        self._name = name
        self._connected = False
        self._config: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    def connect(self, **kwargs) -> None:
        """建立连接"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        ...

    def reset(self) -> None:
        """重置驱动状态"""
        logger.info(f"[{self._name}] 重置驱动")
        if self._connected:
            self.disconnect()
        self.connect(**self._config)

    def __enter__(self):
        self.connect(**self._config)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    def __repr__(self) -> str:
        status = "已连接" if self._connected else "未连接"
        return f"<{self.__class__.__name__}({self._name}) [{status}]>"