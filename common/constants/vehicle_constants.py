"""
Vehicle Constants - 车辆相关常量定义
"""
from enum import Enum, IntEnum


class VehicleState(IntEnum):
    """整车状态"""
    OFF = 0
    ACC = 1         # 附件电源
    ON = 2          # 全车上电
    CRANKING = 3    # 启动中
    RUNNING = 4     # 运行中


class DriveMode(str, Enum):
    """驾驶模式"""
    ECO = "eco"
    COMFORT = "comfort"
    SPORT = "sport"
    SPORT_PLUS = "sport_plus"
    SNOW = "snow"
    OFF_ROAD = "off_road"
    CUSTOM = "custom"


class GearPosition(str, Enum):
    """档位"""
    P = "P"
    R = "R"
    N = "N"
    D = "D"


class ChargingState(str, Enum):
    """充电状态"""
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    CHARGING = "charging"
    CHARGING_COMPLETE = "complete"
    FAULT = "fault"


# 通用阈值
# 注意: 这些阈值已移至 vehicle_profiles.yaml 的 vcu 部分管理
# 此处保留作为向后兼容的默认值
VOLTAGE_12V_NORMAL_RANGE = (11.5, 14.5)    # 12V 电池正常电压范围
VOLTAGE_HV_NORMAL_RANGE = (300, 450)        # 高压电池正常电压范围 (400V平台)
VOLTAGE_HV_800_RANGE = (550, 850)           # 800V 平台电压范围
TEMPERATURE_CABIN_RANGE = (18.0, 28.0)      # 舱内舒适温度范围