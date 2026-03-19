"""
ADB Driver - Android Debug Bridge 驱动
用于与 Android 座舱系统交互 (智能座舱测试核心驱动)

功能:
- Shell 命令执行
- 应用管理 (安装/启动/停止)
- 文件推送/拉取
- 屏幕截图
- 日志获取
- 音频播放控制
- 语音助手状态检测
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from drivers.base_driver import BaseDriver
from common.utils.logger import get_logger
from common.decorators import retry, log_call
from common.exceptions import ADBConnectionError

logger = get_logger("driver.adb")


class ADBDriver(BaseDriver):
    """
    ADB 驱动 - 座舱 Android 系统交互

    支持真机和 Mock 两种模式:
    - 真机模式: 通过 adb 命令行或 adbutils 库与设备通信
    - Mock 模式: 模拟返回，用于 CI/仿真环境
    """

    def __init__(
        self,
        serial: str = "",
        host: str = "127.0.0.1",
        port: int = 5037,
        mock: bool = False,
        command_timeout: int = 30,
    ):
        super().__init__(name=f"ADB({serial or 'default'})")
        self._serial = serial
        self._host = host
        self._port = port
        self._mock = mock
        self._command_timeout = command_timeout
        self._device = None
        self._config = {"serial": serial, "host": host, "port": port}

    # ---------- 生命周期 ----------

    def connect(self, **kwargs) -> None:
        """连接 ADB 设备"""
        if self._mock:
            logger.info(f"[{self._name}] Mock 模式连接")
            self._connected = True
            return

        try:
            # 优先使用 adbutils 库
            try:
                import adbutils
                client = adbutils.AdbClient(host=self._host, port=self._port)
                devices = client.device_list()
                if not devices:
                    raise ADBConnectionError("未发现 ADB 设备")
                self._device = devices[0] if not self._serial else client.device(self._serial)
                self._connected = True
                logger.info(f"[{self._name}] 已连接设备: {self._device.serial}")
            except ImportError:
                # 降级使用命令行
                result = self._run_adb_cmd("devices")
                if "device" in result:
                    self._connected = True
                    logger.info(f"[{self._name}] 命令行模式连接成功")
                else:
                    raise ADBConnectionError("ADB 命令行无可用设备")
        except ADBConnectionError:
            raise
        except Exception as e:
            raise ADBConnectionError(f"ADB 连接失败: {e}")

    def disconnect(self) -> None:
        """断开 ADB 连接"""
        self._device = None
        self._connected = False
        logger.info(f"[{self._name}] 已断开")

    # ---------- Shell 命令 ----------

    def shell(self, command: str) -> str:
        """
        执行 ADB Shell 命令

        Args:
            command: shell 命令字符串

        Returns:
            命令输出
        """
        if self._mock:
            return self._mock_shell(command)

        if self._device:
            output = self._device.shell(command, timeout=self._command_timeout)
            return output if isinstance(output, str) else output.decode("utf-8", errors="replace")
        else:
            return self._run_adb_cmd(f"shell {command}")

    def shell_bool(self, command: str) -> bool:
        """执行 Shell 命令并返回布尔结果 (exit code == 0 为 True)"""
        try:
            self.shell(command)
            return True
        except Exception:
            return False

    # ---------- 应用管理 ----------

    def start_app(self, package: str, activity: str = "") -> None:
        """启动应用"""
        if activity:
            self.shell(f"am start -n {package}/{activity}")
        else:
            self.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
        logger.info(f"[{self._name}] 启动应用: {package}")

    def stop_app(self, package: str) -> None:
        """停止应用"""
        self.shell(f"am force-stop {package}")

    def is_app_running(self, package: str) -> bool:
        """检查应用是否在运行"""
        output = self.shell(f"pidof {package}")
        return bool(output.strip())

    # ---------- 音频相关 (语音测试核心) ----------

    def play_audio(self, remote_path: str) -> None:
        """
        在设备上播放音频文件

        Args:
            remote_path: 设备上的音频文件路径
        """
        self.shell(f"am start -a android.intent.action.VIEW -d file://{remote_path} -t audio/*")
        logger.debug(f"[{self._name}] 播放音频: {remote_path}")

    def play_audio_via_media(self, remote_path: str) -> None:
        """通过 MediaPlayer 播放音频"""
        # 使用 am broadcast 触发播放
        self.shell(
            f'am broadcast -a com.test.PLAY_AUDIO --es path "{remote_path}"'
        )

    def stop_audio(self) -> None:
        """停止音频播放"""
        self.shell("am broadcast -a com.test.STOP_AUDIO")
        self.shell("input keyevent KEYCODE_MEDIA_STOP")

    def push_file(self, local_path: str, remote_path: str) -> None:
        """推送文件到设备"""
        if self._mock:
            logger.debug(f"[{self._name}] Mock 推送: {local_path} → {remote_path}")
            return

        if self._device:
            self._device.push(local_path, remote_path)
        else:
            self._run_adb_cmd(f"push {local_path} {remote_path}")
        logger.debug(f"[{self._name}] 文件已推送: {remote_path}")

    def pull_file(self, remote_path: str, local_path: str) -> None:
        """从设备拉取文件"""
        if self._mock:
            logger.debug(f"[{self._name}] Mock 拉取: {remote_path} → {local_path}")
            return

        if self._device:
            self._device.pull(remote_path, local_path)
        else:
            self._run_adb_cmd(f"pull {remote_path} {local_path}")

    # ---------- 语音助手状态检测 ----------

    def get_voice_assistant_state(self) -> str:
        """
        获取语音助手当前状态

        Returns:
            状态字符串: "idle" / "listening" / "processing" / "speaking" / "error"
        """
        # 通过 dumpsys 获取语音助手状态
        output = self.shell("dumpsys activity services | grep -i voice")
        if "listening" in output.lower():
            return "listening"
        elif "processing" in output.lower():
            return "processing"
        elif "speaking" in output.lower():
            return "speaking"
        return "idle"

    def check_voice_wakeup_response(self) -> bool:
        """
        检测语音助手是否被成功唤醒

        Returns:
            True 表示唤醒成功
        """
        state = self.get_voice_assistant_state()
        return state in ("listening", "processing")

    def get_logcat(self, tag: str = "", lines: int = 100) -> str:
        """获取 logcat 日志"""
        cmd = f"logcat -d -t {lines}"
        if tag:
            cmd += f" -s {tag}"
        return self.shell(cmd)

    def get_voice_wakeup_log(self, lines: int = 50) -> str:
        """获取语音唤醒相关日志"""
        return self.shell(
            f"logcat -d -t {lines} | grep -iE 'wakeup|wake_up|voice_assist|hotword'"
        )

    def take_screenshot(self, local_path: str) -> None:
        """截图并保存到本地"""
        remote_path = "/sdcard/screenshot_tmp.png"
        self.shell(f"screencap -p {remote_path}")
        self.pull_file(remote_path, local_path)
        self.shell(f"rm {remote_path}")

    # ---------- 内部方法 ----------

    def _run_adb_cmd(self, cmd: str) -> str:
        """通过命令行执行 adb 命令"""
        full_cmd = f"adb {'-s ' + self._serial if self._serial else ''} {cmd}"
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=self._command_timeout,
        )
        if result.returncode != 0 and result.stderr:
            logger.warning(f"ADB 命令输出 stderr: {result.stderr.strip()}")
        return result.stdout.strip()

    def _mock_shell(self, command: str) -> str:
        """Mock 模式下的 Shell 命令返回"""
        logger.debug(f"[{self._name}] Mock Shell: {command}")

        # 模拟语音助手状态查询
        if "dumpsys" in command and "voice" in command:
            return "ServiceRecord: VoiceAssistant state=listening"

        # 模拟 logcat 唤醒日志
        if "logcat" in command and ("wakeup" in command.lower() or "wake_up" in command.lower()):
            return (
                "I/VoiceWakeup: Hotword detected, confidence=0.92\n"
                "I/VoiceAssist: Wake up triggered, entering listening mode"
            )

        # 模拟 pidof
        if "pidof" in command:
            return "12345"

        return ""