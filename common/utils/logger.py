"""
Logger - 结构化日志封装
基于 loguru，支持多级别输出、文件轮转、结构化字段
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger


def _setup_default_logger() -> None:
    """初始化默认日志配置"""
    logger.remove()  # 清除默认 handler

    # Windows 终端强制 UTF-8 输出，避免中文乱码
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 控制台输出 - 彩色格式
    logger.add(
        sys.stdout,
        level="INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出 - 按天轮转
    log_dir = Path(__file__).resolve().parent.parent.parent / "reports" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_dir / "test_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[module]}:{function}:{line} | {message}",
        rotation="1 day",
        retention="30 days",
        encoding="utf-8",
    )


# 初始化
_setup_default_logger()


def get_logger(name: str = "automotive_test") -> Any:
    """
    获取绑定了模块名的 logger 实例

    日志格式中通过 {extra[module]} 显示此名称

    Args:
        name: 模块名称

    Returns:
        loguru logger 实例
    """
    return logger.bind(module=name)