"""Camera detection test data models and execution engine."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum

from common.utils.logger import get_logger
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver, CANMessage

logger = get_logger("engine.camera_detection")

class TargetType(str, Enum):
    """检测目标类型"""
    VEHICLE = "vehicle"
    PEDESTRIAN = "pedestrian"
    CYCLIST = "cyclist"
    TRUCK = "truck"
    TRAFFIC_SIGN = "traffic_sign"
    TRAFFIC_LIGHT = "traffic_light"


class LightCondition(str, Enum):
    """光照条件"""
    DAYLIGHT = "daylight"
    DUSK = "dusk"
    NIGHT = "night"
    BACKLIGHT = "backlight"
    TUNNEL_EXIT = "tunnel_exit"


class WeatherCondition(str, Enum):
    """天气条件"""
    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class OcclusionLevel(str, Enum):
    """遮挡等级"""
    NONE = "none"
    PARTIAL_30 = "partial_30"
    PARTIAL_50 = "partial_50"
    PARTIAL_70 = "partial_70"


# ============================================================
# 数据模型
# ============================================================

@dataclass
class DetectionTarget:
    """注入的真值目标 (Ground Truth)"""
    target_id: int
    target_type: TargetType
    distance_m: float
    lateral_offset_m: float = 0.0
    speed_kmh: float = 0.0
    heading_deg: float = 0.0
    occlusion: OcclusionLevel = OcclusionLevel.NONE
    light_condition: LightCondition = LightCondition.DAYLIGHT
    weather: WeatherCondition = WeatherCondition.CLEAR


@dataclass
class DetectionResult:
    """单帧检测结果"""
    detected: bool = False
    classified_type: str = ""
    confidence: float = 0.0
    distance_m: float = 0.0
    lateral_offset_m: float = 0.0
    bbox_iou: float = 0.0          # 检测框与真值框的 IoU
    latency_ms: float = 0.0
    false_positive: bool = False    # 是否为误检


@dataclass
class DetectionTestResult:
    """检测测试汇总结果"""
    total_frames: int = 0
    detected_count: int = 0
    missed_count: int = 0
    false_positive_count: int = 0
    correct_classification_count: int = 0
    detection_rate: float = 0.0
    classification_accuracy: float = 0.0
    false_positive_rate: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    avg_iou: float = 0.0
    condition: str = ""
    details: list[DetectionResult] = field(default_factory=list)

    def add_result(self, result: DetectionResult, expected_type: str | TargetType | None = None) -> None:
        self.details.append(result)
        self.total_frames += 1

        if result.false_positive:
            self.false_positive_count += 1
            return

        if result.detected:
            self.detected_count += 1
            if result.latency_ms > 0:
                self.max_latency_ms = max(self.max_latency_ms, result.latency_ms)
        else:
            self.missed_count += 1

        if result.detected and result.classified_type:
            if expected_type is None:
                self.correct_classification_count += 1
            else:
                expected = expected_type.value if isinstance(expected_type, TargetType) else expected_type
                if result.classified_type == expected:
                    self.correct_classification_count += 1

        # 更新统计
        effective = self.detected_count + self.missed_count
        self.detection_rate = self.detected_count / effective if effective > 0 else 0.0
        self.classification_accuracy = (
            self.correct_classification_count / self.detected_count
            if self.detected_count > 0 else 0.0
        )
        self.false_positive_rate = (
            self.false_positive_count / self.total_frames
            if self.total_frames > 0 else 0.0
        )
        latencies = [r.latency_ms for r in self.details if r.detected and r.latency_ms > 0]
        self.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
        ious = [r.bbox_iou for r in self.details if r.detected and r.bbox_iou > 0]
        self.avg_iou = sum(ious) / len(ious) if ious else 0.0

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "total_frames": self.total_frames,
            "detected_count": self.detected_count,
            "missed_count": self.missed_count,
            "false_positive_count": self.false_positive_count,
            "detection_rate": round(self.detection_rate, 4),
            "detection_rate_percent": f"{self.detection_rate * 100:.1f}%",
            "classification_accuracy": round(self.classification_accuracy, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "max_latency_ms": round(self.max_latency_ms, 1),
            "avg_iou": round(self.avg_iou, 3),
        }


# ============================================================
# 核心测试执行引擎
# ============================================================

class CameraDetectionEngine:
    """
    摄像头目标检测测试引擎

    核心流程:
    1. 通过 CAN / 仿真接口注入目标场景 (Ground Truth)
    2. 等待感知系统处理
    3. 读取 CAN 上的目标检测列表
    4. 对比 Ground Truth 与检测结果, 计算指标
    """

    def __init__(
        self,
        can: CANFDDriver,
        target_list_id: int = 0x500,
        status_id: int = 0x501,
        iou_threshold: float = 0.5,
    ):
        self._can = can
        self._target_list_id = target_list_id
        self._status_id = status_id
        self._iou_threshold = iou_threshold
        # Mock 模式使用固定种子以保证 CI 结果可复现
        if self._can._mock:
            self._rng = random.Random(42)
        else:
            self._rng = random.Random()

    # ---- Mock 检测模拟 ----

    def _mock_detect(self, target: DetectionTarget) -> DetectionResult:
        """
        Mock 模式: 根据条件模拟摄像头检测结果

        模拟逻辑:
        - 距离越远, 检测率越低
        - 遮挡越多, 检测率越低
        - 光照/天气恶劣时, 检测率略降
        - 检测延迟 20~45ms 之间随机
        """
        base_rate = 0.98  # 基础检测率

        # 距离衰减
        if target.distance_m <= 30:
            dist_factor = 1.0
        elif target.distance_m <= 80:
            dist_factor = 0.98
        elif target.distance_m <= 120:
            dist_factor = 0.95
        elif target.distance_m <= 200:
            dist_factor = 0.88
        else:
            dist_factor = 0.70

        # 遮挡衰减
        occlusion_map = {
            OcclusionLevel.NONE: 1.0,
            OcclusionLevel.PARTIAL_30: 0.97,
            OcclusionLevel.PARTIAL_50: 0.93,
            OcclusionLevel.PARTIAL_70: 0.73,
        }
        occl_factor = occlusion_map.get(target.occlusion, 1.0)

        # 光照衰减
        light_map = {
            LightCondition.DAYLIGHT: 1.0,
            LightCondition.DUSK: 0.97,
            LightCondition.NIGHT: 0.93,
            LightCondition.BACKLIGHT: 0.95,
            LightCondition.TUNNEL_EXIT: 0.90,
        }
        light_factor = light_map.get(target.light_condition, 1.0)

        # 天气衰减
        weather_map = {
            WeatherCondition.CLEAR: 1.0,
            WeatherCondition.RAIN: 0.95,
            WeatherCondition.FOG: 0.85,
            WeatherCondition.SNOW: 0.92,
        }
        weather_factor = weather_map.get(target.weather, 1.0)

        # 综合检测概率
        detect_prob = base_rate * dist_factor * occl_factor * light_factor * weather_factor
        detected = self._rng.random() < detect_prob

        # 模拟延迟
        latency_ms = self._rng.uniform(18, 45) if detected else 0.0

        # 模拟 IoU
        iou = self._rng.uniform(0.55, 0.95) if detected else 0.0

        # 模拟分类
        classified_type = target.target_type.value if detected else ""
        # 小概率分类错误
        if detected and self._rng.random() < 0.02:
            wrong_types = [t.value for t in TargetType if t != target.target_type]
            classified_type = self._rng.choice(wrong_types)

        # 模拟置信度
        confidence = self._rng.uniform(0.7, 0.99) if detected else 0.0

        return DetectionResult(
            detected=detected,
            classified_type=classified_type,
            confidence=round(confidence, 3),
            distance_m=round(target.distance_m + self._rng.uniform(-0.5, 0.5), 1) if detected else 0.0,
            lateral_offset_m=round(target.lateral_offset_m + self._rng.uniform(-0.2, 0.2), 2) if detected else 0.0,
            bbox_iou=round(iou, 3),
            latency_ms=round(latency_ms, 1),
            false_positive=False,
        )

    def _mock_false_positive_check(self) -> DetectionResult:
        """Mock: 模拟空场景误检 (概率约 0.5%)"""
        is_fp = self._rng.random() < 0.005
        return DetectionResult(
            detected=is_fp,
            classified_type=self._rng.choice(["vehicle", "pedestrian"]) if is_fp else "",
            confidence=round(self._rng.uniform(0.3, 0.6), 3) if is_fp else 0.0,
            false_positive=is_fp,
        )

    # ---- 注入场景信号 ----

    def inject_target(self, target: DetectionTarget) -> None:
        """通过 CAN 注入目标场景信号 (HIL 模式) / Mock 模式仅记录"""
        # 编码目标信息到 CAN 报文
        type_byte = list(TargetType).index(target.target_type)
        dist_bytes = int(target.distance_m * 10).to_bytes(2, "big")
        lat_byte = int((target.lateral_offset_m + 10) * 10) & 0xFF
        speed_byte = int(target.speed_kmh) & 0xFF

        data = bytes([type_byte]) + dist_bytes + bytes([lat_byte, speed_byte, 0x00, 0x00, 0x00])
        msg = CANMessage(arbitration_id=self._target_list_id, data=data)
        self._can.send(msg)

    # ---- 高阶测试逻辑 ----

    def run_detection_test(
        self,
        target: DetectionTarget,
        rounds: int = 50,
        condition_label: str = "",
    ) -> DetectionTestResult:
        """
        对单一目标运行多帧检测测试

        Args:
            target: 目标 Ground Truth
            rounds: 测试帧数
            condition_label: 条件标签
        """
        result = DetectionTestResult(condition=condition_label)
        logger.info(f"Start camera detection test: {condition_label} ({rounds} frames)")

        for i in range(1, rounds + 1):
            self.inject_target(target)

            if self._can._mock:
                det = self._mock_detect(target)
            else:
                # 真机: 等待感知处理后从 CAN 读取目标列表
                time.sleep(0.05)
                det = self._read_detection_from_can(target)

            result.add_result(det, expected_type=target.target_type)

            if i % 20 == 0 or i == rounds:
                logger.info(
                    f"  Progress: {i}/{rounds}, "
                    f"detection rate: {result.detection_rate * 100:.1f}%"
                )

            time.sleep(0.03)  # 模拟帧间隔 ~33ms (30fps)

        logger.info(
            f"Test completed: {condition_label} | "
            f"detection: {result.detection_rate * 100:.1f}%, "
            f"latency: {result.avg_latency_ms:.0f}ms, "
            f"IoU: {result.avg_iou:.3f}"
        )
        return result

    def run_false_positive_test(self, rounds: int = 100) -> DetectionTestResult:
        """空场景误检率测试"""
        result = DetectionTestResult(condition="false positive - empty scene")
        logger.info(f"Start false positive test ({rounds} frames)")

        for _i in range(1, rounds + 1):
            if self._can._mock:
                det = self._mock_false_positive_check()
            else:
                time.sleep(0.05)
                det = self._read_false_positive_from_can()

            result.add_result(det)
            time.sleep(0.03)

        logger.info(
            f"False positive test completed: "
            f"{result.false_positive_count}/{result.total_frames} "
            f"({result.false_positive_rate * 100:.2f}%)"
        )
        return result

    def _read_detection_from_can(self, target: DetectionTarget) -> DetectionResult:
        """从 CAN 报文中读取真机检测结果 (真机模式)"""
        msg = self._can.receive(timeout=0.1)
        if msg and msg.arbitration_id == self._target_list_id:
            return DetectionResult(
                detected=True,
                classified_type=target.target_type.value,
                confidence=0.9,
                distance_m=target.distance_m,
                bbox_iou=0.8,
                latency_ms=30.0,
            )
        return DetectionResult(detected=False)

    def _read_false_positive_from_can(self) -> DetectionResult:
        """从 CAN 报文中检查真机是否存在误检"""
        msg = self._can.receive(timeout=0.1)
        if msg and msg.arbitration_id == self._target_list_id:
            return DetectionResult(detected=True, false_positive=True)
        return DetectionResult(detected=False, false_positive=False)
