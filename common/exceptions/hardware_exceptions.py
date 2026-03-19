"""
Hardware Exceptions - 硬件设备自定义异常
"""


class HardwareException(Exception):
    """硬件异常基类"""
    pass


class HILConnectionError(HardwareException):
    """HIL 系统连接异常"""
    pass


class PowerSupplyError(HardwareException):
    """电源设备异常"""
    pass


class MeasurementError(HardwareException):
    """测量设备异常"""
    pass