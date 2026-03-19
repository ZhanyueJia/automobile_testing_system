"""
Vehicle Exceptions - 车辆相关自定义异常
"""


class VehicleException(Exception):
    """车辆相关异常基类"""
    pass


class VehicleConnectionError(VehicleException):
    """车辆连接异常"""
    pass


class VehicleStateError(VehicleException):
    """车辆状态异常 (如: 未上电)"""
    pass


class VehicleConfigError(VehicleException):
    """车辆配置异常"""
    pass