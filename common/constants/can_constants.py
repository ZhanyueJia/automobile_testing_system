"""
CAN Constants - CAN 协议相关常量
"""


class CANConstants:
    """CAN 总线常量"""

    # 标准帧 / 扩展帧
    STANDARD_ID_MAX = 0x7FF
    EXTENDED_ID_MAX = 0x1FFFFFFF

    # CAN FD 数据长度码
    FD_DLC_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
                  8: 8, 9: 12, 10: 16, 11: 20, 12: 24, 13: 32, 14: 48, 15: 64}

    # 常用波特率
    BITRATE_125K = 125000
    BITRATE_250K = 250000
    BITRATE_500K = 500000
    BITRATE_1M = 1000000

    # CAN FD 数据段波特率
    FD_BITRATE_2M = 2000000
    FD_BITRATE_5M = 5000000
    FD_BITRATE_8M = 8000000

    # 超时
    DEFAULT_TIMEOUT = 1.0
    DIAG_TIMEOUT = 5.0