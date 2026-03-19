"""
ADAS Constants - 智能驾驶相关常量
"""
from enum import Enum, IntEnum


class ADASLevel(IntEnum):
    """自动驾驶等级"""
    L0 = 0  # 无自动化
    L1 = 1  # 驾驶辅助
    L2 = 2  # 部分自动化
    L3 = 3  # 有条件自动化
    L4 = 4  # 高度自动化
    L5 = 5  # 完全自动化


class AEBState(str, Enum):
    """AEB 自动紧急制动状态"""
    STANDBY = "standby"
    WARNING = "warning"
    PARTIAL_BRAKE = "partial_brake"
    FULL_BRAKE = "full_brake"
    RELEASED = "released"


class ACCState(str, Enum):
    """ACC 自适应巡航状态"""
    OFF = "off"
    STANDBY = "standby"
    ACTIVE = "active"
    OVERRIDE = "override"
    FAULT = "fault"


# 性能要求阈值
MAX_SYSTEM_RESPONSE_MS = 100        # 系统最大响应时间
MAX_PERCEPTION_LATENCY_MS = 50      # 感知最大延迟
MAX_PLANNING_CYCLE_MS = 100         # 规划周期
MIN_DETECTION_ACCURACY = 0.95       # 最低检测准确率
AEB_MAX_TTC_S = 3.0                 # AEB 最大碰撞时间