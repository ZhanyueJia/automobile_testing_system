"""
CAN-FD Driver - CAN / CAN-FD 总线通信驱动
支持报文收发、信号编解码、DBC 文件解析
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from drivers.base_driver import BaseDriver
from common.utils.logger import get_logger
from common.decorators import retry, log_call

logger = get_logger("driver.can_fd")


class CANMessage:
    """CAN 报文数据结构"""

    def __init__(
        self,
        arbitration_id: int,
        data: bytes,
        is_extended_id: bool = False,
        is_fd: bool = False,
        timestamp: float = 0.0,
    ):
        self.arbitration_id = arbitration_id
        self.data = data
        self.is_extended_id = is_extended_id
        self.is_fd = is_fd
        self.timestamp = timestamp

    def __repr__(self) -> str:
        hex_data = " ".join(f"{b:02X}" for b in self.data)
        return f"<CAN {'FD ' if self.is_fd else ''}0x{self.arbitration_id:03X} [{len(self.data)}] {hex_data}>"


class CANFDDriver(BaseDriver):
    """
    CAN / CAN-FD 总线驱动

    支持:
    - 标准 CAN 和 CAN-FD 通信
    - DBC 文件信号编解码
    - 报文过滤与监听
    - Mock 模式 (仿真无硬件环境)
    """

    def __init__(
        self,
        interface: str = "socketcan",
        channel: str = "can0",
        bitrate: int = 500000,
        fd: bool = True,
        data_bitrate: int = 2000000,
        mock: bool = False,
    ):
        super().__init__(name=f"CAN-FD({channel})")
        self._interface = interface
        self._channel = channel
        self._bitrate = bitrate
        self._fd = fd
        self._data_bitrate = data_bitrate
        self._mock = mock
        self._bus = None
        self._db = None  # cantools Database
        self._config = {
            "interface": interface,
            "channel": channel,
            "bitrate": bitrate,
        }

    def connect(self, **kwargs) -> None:
        """连接 CAN 总线"""
        if self._mock:
            logger.info(f"[{self._name}] Mock 模式连接")
            self._connected = True
            return

        try:
            import can
            self._bus = can.Bus(
                interface=self._interface,
                channel=self._channel,
                bitrate=self._bitrate,
                fd=self._fd,
                data_bitrate=self._data_bitrate,
            )
            self._connected = True
            logger.info(f"[{self._name}] 已连接 ({self._bitrate} baud)")
        except Exception as e:
            logger.error(f"[{self._name}] 连接失败: {e}")
            raise

    def disconnect(self) -> None:
        """断开 CAN 总线"""
        if self._bus:
            self._bus.shutdown()
            self._bus = None
        self._connected = False
        logger.info(f"[{self._name}] 已断开")

    def load_dbc(self, dbc_path: str | Path) -> None:
        """加载 DBC 信号定义文件"""
        try:
            import cantools
            self._db = cantools.database.load_file(str(dbc_path))
            logger.info(f"[{self._name}] 已加载 DBC: {dbc_path} (共 {len(self._db.messages)} 条报文)")
        except Exception as e:
            logger.error(f"[{self._name}] DBC 加载失败: {e}")
            raise

    def send(self, msg: CANMessage) -> None:
        """发送 CAN 报文"""
        if self._mock:
            logger.debug(f"[{self._name}] Mock 发送: {msg}")
            return

        if not self._bus:
            raise RuntimeError("CAN 总线未连接")
        import can
        can_msg = can.Message(
            arbitration_id=msg.arbitration_id,
            data=msg.data,
            is_extended_id=msg.is_extended_id,
            is_fd=msg.is_fd,
        )
        self._bus.send(can_msg)

    def receive(self, timeout: float = 1.0) -> Optional[CANMessage]:
        """接收 CAN 报文"""
        if self._mock:
            return None

        if not self._bus:
            raise RuntimeError("CAN 总线未连接")

        msg = self._bus.recv(timeout=timeout)
        if msg is None:
            return None
        return CANMessage(
            arbitration_id=msg.arbitration_id,
            data=bytes(msg.data),
            is_extended_id=msg.is_extended_id,
            is_fd=msg.is_fd,
            timestamp=msg.timestamp,
        )

    def encode_signal(self, message_name: str, signals: dict[str, Any]) -> CANMessage:
        """
        使用 DBC 定义编码信号到 CAN 报文

        Args:
            message_name: DBC 中的报文名称
            signals: 信号名-值字典
        """
        if not self._db:
            raise RuntimeError("未加载 DBC 文件")

        db_msg = self._db.get_message_by_name(message_name)
        data = db_msg.encode(signals)
        return CANMessage(
            arbitration_id=db_msg.frame_id,
            data=data,
            is_fd=len(data) > 8,
        )

    def decode_signal(self, msg: CANMessage) -> dict[str, Any]:
        """
        使用 DBC 定义解码 CAN 报文中的信号

        Args:
            msg: CAN 报文

        Returns:
            信号名-值字典
        """
        if not self._db:
            raise RuntimeError("未加载 DBC 文件")

        db_msg = self._db.get_message_by_frame_id(msg.arbitration_id)
        return db_msg.decode(msg.data)