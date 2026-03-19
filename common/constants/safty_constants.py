"""
Safety Constants - 安全相关常量
参考 ISO 26262 功能安全等级
"""
from enum import Enum


class SafetyLevel(str, Enum):
    """ASIL 功能安全等级 (ISO 26262)"""
    QM = "QM"       # 质量管理
    ASIL_A = "A"
    ASIL_B = "B"
    ASIL_C = "C"
    ASIL_D = "D"    # 最高安全等级


class FailureType(str, Enum):
    """故障类型"""
    TRANSIENT = "transient"         # 瞬态故障
    PERMANENT = "permanent"         # 永久故障
    INTERMITTENT = "intermittent"   # 间歇性故障


# 安全相关阈值
MAX_GLANCE_TIME_S = 1.2            # 驾驶员最大视线偏离时间
MAX_DRIVER_DISTRACTION_S = 2.0     # 最大分心时间
EMERGENCY_BRAKE_DECEL = 9.8        # 紧急制动最大减速度 (m/s²)