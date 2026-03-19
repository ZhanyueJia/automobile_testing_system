"""
DataConverter - 数据格式转换工具
支持 CAN 信号、物理值、工程值之间的转换
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any


class DataConverter:
    """汽车测试数据格式转换"""

    @staticmethod
    def raw_to_physical(raw_value: int, factor: float, offset: float) -> float:
        """CAN 原始值 → 物理值: physical = raw * factor + offset"""
        return raw_value * factor + offset

    @staticmethod
    def physical_to_raw(physical_value: float, factor: float, offset: float) -> int:
        """物理值 → CAN 原始值: raw = (physical - offset) / factor"""
        return int((physical_value - offset) / factor)

    @staticmethod
    def bytes_to_hex_string(data: bytes) -> str:
        """字节流转十六进制字符串"""
        return " ".join(f"{b:02X}" for b in data)

    @staticmethod
    def hex_string_to_bytes(hex_str: str) -> bytes:
        """十六进制字符串转字节流"""
        return bytes.fromhex(hex_str.replace(" ", ""))

    @staticmethod
    def celsius_to_fahrenheit(celsius: float) -> float:
        return celsius * 9.0 / 5.0 + 32.0

    @staticmethod
    def kmh_to_ms(kmh: float) -> float:
        """km/h → m/s"""
        return kmh / 3.6

    @staticmethod
    def load_json(path: str | Path) -> Any:
        """加载 JSON 文件"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_json(data: Any, path: str | Path) -> None:
        """保存 JSON 文件"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def pack_can_signal(
        value: int, start_bit: int, length: int, byte_order: str = "little_endian"
    ) -> int:
        """将信号值打包到 CAN 数据帧的对应位位置"""
        mask = (1 << length) - 1
        value &= mask
        if byte_order == "little_endian":
            return value << start_bit
        else:
            return value << (64 - start_bit - length)