"""
AudioPlayer - 音频播放控制抽象
用于唤醒词/语音命令的音频文件播放控制
支持本地播放和远程设备播放两种模式
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from common.utils.logger import get_logger

logger = get_logger("driver.audio_player")


class AudioPlayMode(str, Enum):
    """音频播放模式"""
    LOCAL = "local"           # 本地 PC 音箱播放 (外放到车内麦克风)
    ADB_INJECT = "adb_inject"  # ADB 注入音频到座舱
    SIMULATOR = "simulator"    # 仿真模式 (无实际播放)


@dataclass
class AudioFile:
    """音频文件描述"""
    path: str                    # 文件路径
    description: str = ""        # 描述 (如 "唤醒词-安静环境")
    duration_s: float = 0.0      # 时长 (秒)
    noise_level_db: int = 0      # 背景噪声等级
    distance_m: float = 1.0      # 模拟距离
    zone: str = "driver"         # 音区
    tags: list[str] = field(default_factory=list)


class AudioPlayer:
    """
    音频播放控制器

    根据测试环境选择播放方式:
    - LOCAL: 通过 PC 声卡播放到外部音箱 (真实环境)
    - ADB_INJECT: 通过 ADB 将音频注入座舱设备 (HIL 环境)
    - SIMULATOR: 仿真模式，不实际播放但模拟延时
    """

    def __init__(self, mode: AudioPlayMode = AudioPlayMode.SIMULATOR, adb_driver=None):
        self._mode = mode
        self._adb = adb_driver
        self._is_playing = False
        logger.info(f"AudioPlayer 初始化, 模式: {mode.value}")

    def play(self, audio: AudioFile, wait: bool = True) -> None:
        """
        播放音频文件

        Args:
            audio: 音频文件信息
            wait: 是否等待播放完成
        """
        logger.info(f"播放音频: {audio.path} (模式: {self._mode.value})")
        self._is_playing = True

        if self._mode == AudioPlayMode.LOCAL:
            self._play_local(audio.path)
        elif self._mode == AudioPlayMode.ADB_INJECT:
            self._play_adb(audio.path)
        elif self._mode == AudioPlayMode.SIMULATOR:
            self._play_simulated(audio)

        if wait and audio.duration_s > 0:
            time.sleep(audio.duration_s)

        self._is_playing = False

    def stop(self) -> None:
        """停止播放"""
        if self._mode == AudioPlayMode.ADB_INJECT and self._adb:
            self._adb.stop_audio()
        self._is_playing = False

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def _play_local(self, file_path: str) -> None:
        """通过本地声卡播放"""
        try:
            # Windows: 使用 PowerShell 播放
            import platform
            if platform.system() == "Windows":
                subprocess.Popen(
                    ["powershell", "-c", f'(New-Object Media.SoundPlayer "{file_path}").PlaySync()'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["aplay", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as e:
            logger.warning(f"本地播放失败: {e}, 降级为仿真模式")

    def _play_adb(self, file_path: str) -> None:
        """通过 ADB 注入播放"""
        if not self._adb:
            logger.warning("ADB 驱动未初始化，跳过播放")
            return
        # 推送文件到设备临时目录
        remote_path = f"/sdcard/test_audio/{Path(file_path).name}"
        self._adb.push_file(file_path, remote_path)
        self._adb.play_audio(remote_path)

    def _play_simulated(self, audio: AudioFile) -> None:
        """仿真模式 - 记录日志但不实际播放"""
        logger.debug(
            f"[仿真] 播放唤醒词音频: zone={audio.zone}, "
            f"noise={audio.noise_level_db}dB, distance={audio.distance_m}m"
        )