"""
Network Exceptions - 网络通信自定义异常
"""


class NetworkException(Exception):
    """网络通信异常基类"""
    pass


class CANBusError(NetworkException):
    """CAN 总线通信异常"""
    pass


class ADBConnectionError(NetworkException):
    """ADB 连接异常"""
    pass


class SOMEIPError(NetworkException):
    """SOME/IP 协议异常"""
    pass


class DoIPError(NetworkException):
    """DoIP 诊断协议异常"""
    pass


class MQTTError(NetworkException):
    """MQTT 通信异常"""
    pass