"""
SignalProcessor - 信号处理算法
用于音频、CAN 信号的分析处理
"""
from __future__ import annotations

import math
from typing import Sequence


class SignalProcessor:
    """信号处理工具"""

    @staticmethod
    def calculate_rms(samples: Sequence[float]) -> float:
        """计算信号均方根值 (RMS)"""
        if not samples:
            return 0.0
        return math.sqrt(sum(s * s for s in samples) / len(samples))

    @staticmethod
    def calculate_snr_db(signal_power: float, noise_power: float) -> float:
        """计算信噪比 (dB)"""
        if noise_power <= 0:
            return float('inf')
        return 10 * math.log10(signal_power / noise_power)

    @staticmethod
    def moving_average(data: Sequence[float], window: int = 5) -> list[float]:
        """滑动平均滤波"""
        if len(data) < window:
            return list(data)
        result = []
        for i in range(len(data) - window + 1):
            avg = sum(data[i:i + window]) / window
            result.append(avg)
        return result

    @staticmethod
    def detect_threshold_crossing(
        data: Sequence[float], threshold: float, direction: str = "rising"
    ) -> list[int]:
        """
        检测信号越过阈值的索引位置

        Args:
            data: 信号数据
            threshold: 阈值
            direction: "rising" 上升沿 / "falling" 下降沿 / "both" 双向

        Returns:
            越过阈值的索引列表
        """
        crossings = []
        for i in range(1, len(data)):
            if direction in ("rising", "both") and data[i - 1] < threshold <= data[i]:
                crossings.append(i)
            if direction in ("falling", "both") and data[i - 1] >= threshold > data[i]:
                crossings.append(i)
        return crossings