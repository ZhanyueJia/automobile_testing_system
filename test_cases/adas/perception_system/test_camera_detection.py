"""
test_camera_detection.py - 摄像头目标检测测试

测试目标:
    验证前视/环视摄像头的目标检测能力在各种条件下满足功能安全与性能要求

测试覆盖维度:
    1. 基础目标检测准确率 (车辆/行人/骑行者/卡车)
    2. 不同距离下的检测能力 (10m ~ 200m)
    3. 检测延迟 (≤50ms)
    4. 多目标同时检测
    5. 遮挡场景检测 (部分遮挡 30%/50%/70%)
    6. 光照条件影响 (白天/黄昏/夜晚/逆光/隧道出入口)
    7. 天气条件影响 (晴天/雨天/雾天/雪天)
    8. 目标分类准确率
    9. 误检率 (False Positive)
    10. 漏检率 (False Negative)

对标竞品:
    特斯拉 FSD / 小鹏 XNGP / 蔚来 NIO Aquila / 问界 HUAWEI ADS

参考标准:
    - Euro NCAP 2025 camera detection requirements
    - ISO 26262 ASIL-B camera perception
    - 检测准确率 ≥ 95%
    - 检测延迟 ≤ 50ms
    - 误检率 ≤ 1%
"""
from __future__ import annotations

import json

import allure
import pytest

from common.utils.logger import get_logger
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver
from test_cases.adas.perception_system.camera_detection_engine import (
    CameraDetectionEngine,
    DetectionTarget,
    LightCondition,
    OcclusionLevel,
    TargetType,
    WeatherCondition,
)

logger = get_logger("test.camera_detection")

# ============================================================
# 测试用例
# ============================================================

@allure.epic("智能驾驶")
@allure.feature("感知系统")
@allure.story("摄像头目标检测")
@pytest.mark.adas
class TestCameraDetection:
    """
    摄像头目标检测测试套件

    验证摄像头感知系统在不同条件下的检测能力:
    - 基础目标检测准确率
    - 不同距离检测能力
    - 检测延迟
    - 多目标类型检测
    - 遮挡场景
    - 光照影响
    - 天气影响
    - 误检率
    - 分类准确率
    """

    @pytest.fixture(autouse=True)
    def setup(self, can: CANFDDriver, perception_config: dict):
        """测试前置: 初始化检测引擎"""
        self.engine = CameraDetectionEngine(
            can=can,
            target_list_id=perception_config["camera_target_list_id"],
            status_id=perception_config["camera_status_id"],
            iou_threshold=perception_config["iou_threshold"],
        )
        self.config = perception_config
        self.min_accuracy = perception_config["detection_accuracy_min"]
        self.max_latency_ms = perception_config["detection_latency_max_ms"]

    def _make_target(
        self,
        target_type: TargetType = TargetType.VEHICLE,
        distance_m: float = 50.0,
        occlusion: OcclusionLevel = OcclusionLevel.NONE,
        light: LightCondition = LightCondition.DAYLIGHT,
        weather: WeatherCondition = WeatherCondition.CLEAR,
    ) -> DetectionTarget:
        """构建检测目标"""
        return DetectionTarget(
            target_id=1,
            target_type=target_type,
            distance_m=distance_m,
            lateral_offset_m=0.5,
            speed_kmh=30.0,
            occlusion=occlusion,
            light_condition=light,
            weather=weather,
        )

    # ----------------------------------------------------------------
    # 1. 基础目标检测准确率
    # ----------------------------------------------------------------

    @allure.title("基础目标检测准确率测试 - 车辆")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_basic_vehicle_detection(self):
        """
        测试场景: 白天晴天, 50m 距离, 无遮挡, 前方车辆
        验证标准: 检测率 ≥ 95%
        """
        target = self._make_target(
            target_type=TargetType.VEHICLE, distance_m=50.0
        )
        rounds = min(self.config["test_rounds"], 50)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label="vehicle-50m-daylight-clear",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Vehicle detection result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.detection_rate >= self.min_accuracy, (
            f"Vehicle detection rate {result.detection_rate * 100:.1f}% "
            f"below threshold {self.min_accuracy * 100:.0f}%"
        )
        logger.info(f"✓ Basic vehicle detection passed: {result.detection_rate * 100:.1f}%")

    @allure.title("基础目标检测准确率测试 - 行人")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_basic_pedestrian_detection(self):
        """
        测试场景: 白天晴天, 30m 距离, 无遮挡, 行人
        验证标准: 检测率 ≥ 95% (Euro NCAP VRU 要求)
        """
        target = self._make_target(
            target_type=TargetType.PEDESTRIAN, distance_m=30.0
        )
        rounds = min(self.config["test_rounds"], 50)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label="pedestrian-30m-daylight-clear",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Pedestrian detection result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.detection_rate >= self.min_accuracy, (
            f"Pedestrian detection rate {result.detection_rate * 100:.1f}% "
            f"below threshold {self.min_accuracy * 100:.0f}%"
        )
        logger.info(f"✓ Basic pedestrian detection passed: {result.detection_rate * 100:.1f}%")

    # ----------------------------------------------------------------
    # 2. 不同距离检测能力
    # ----------------------------------------------------------------

    @allure.title("距离检测能力测试 - {distance_m}m")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("distance_m", [10, 30, 50, 80, 120, 200], ids=[
        "10m-近距离", "30m-AEB有效距离", "50m-标准距离",
        "80m-中距离", "120m-远距离", "200m-极远距离"
    ])
    def test_detection_at_distance(self, distance_m: int):
        """
        测试场景: 不同距离下的车辆检测能力
        验证标准:
            - ≤80m: 检测率 ≥ 95%
            - 80~120m: 检测率 ≥ 90%
            - 120~200m: 检测率 ≥ 80%
        """
        target = self._make_target(
            target_type=TargetType.VEHICLE, distance_m=float(distance_m)
        )
        rounds = min(self.config["test_rounds"], 40)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label=f"vehicle-{distance_m}m",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name=f"Detection at {distance_m}m",
            attachment_type=allure.attachment_type.JSON,
        )

        if distance_m <= 80:
            threshold = self.min_accuracy
        elif distance_m <= 120:
            threshold = 0.90
        else:
            threshold = 0.80

        assert result.detection_rate >= threshold, (
            f"Detection at {distance_m}m: {result.detection_rate * 100:.1f}% "
            f"below threshold {threshold * 100:.0f}%"
        )

    # ----------------------------------------------------------------
    # 3. 检测延迟
    # ----------------------------------------------------------------

    @allure.title("检测延迟测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_detection_latency(self):
        """
        测试场景: 标准条件下检测延迟
        验证标准:
            - 平均延迟 ≤ 50ms
            - 最大延迟 ≤ 100ms
        """
        target = self._make_target(
            target_type=TargetType.VEHICLE, distance_m=50.0
        )
        rounds = min(self.config["test_rounds"], 50)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label="latency-vehicle-50m",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Detection latency result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.avg_latency_ms <= self.max_latency_ms, (
            f"Average latency {result.avg_latency_ms:.1f}ms "
            f"exceeds threshold {self.max_latency_ms}ms"
        )
        assert result.max_latency_ms <= self.max_latency_ms * 2, (
            f"Max latency {result.max_latency_ms:.1f}ms "
            f"exceeds {self.max_latency_ms * 2}ms"
        )
        logger.info(
            f"✓ Latency test passed: avg={result.avg_latency_ms:.0f}ms, "
            f"max={result.max_latency_ms:.0f}ms"
        )

    # ----------------------------------------------------------------
    # 4. 多目标类型检测
    # ----------------------------------------------------------------

    @allure.title("多目标类型检测 - {target_type}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("target_type", [
        TargetType.VEHICLE, TargetType.PEDESTRIAN, TargetType.CYCLIST,
        TargetType.TRUCK, TargetType.TRAFFIC_SIGN, TargetType.TRAFFIC_LIGHT,
    ], ids=["vehicle", "pedestrian", "cyclist", "truck", "traffic_sign", "traffic_light"])
    def test_target_type_detection(self, target_type: TargetType):
        """
        测试场景: 不同目标类型的检测能力
        验证标准: 所有类型检测率 ≥ 90%
        """
        distance = 30.0 if target_type in (TargetType.PEDESTRIAN, TargetType.CYCLIST) else 50.0
        target = self._make_target(target_type=target_type, distance_m=distance)
        rounds = min(self.config["test_rounds"], 30)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label=f"{target_type.value}-{distance}m",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name=f"{target_type.value} detection",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.detection_rate >= 0.90, (
            f"{target_type.value} detection rate {result.detection_rate * 100:.1f}% below 90%"
        )

    # ----------------------------------------------------------------
    # 5. 遮挡场景检测
    # ----------------------------------------------------------------

    @allure.title("遮挡场景检测 - {occlusion}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("occlusion", [
        OcclusionLevel.NONE, OcclusionLevel.PARTIAL_30,
        OcclusionLevel.PARTIAL_50, OcclusionLevel.PARTIAL_70,
    ], ids=["no-occlusion", "30%-occluded", "50%-occluded", "70%-occluded"])
    def test_occlusion_detection(self, occlusion: OcclusionLevel):
        """
        测试场景: 不同遮挡程度下的检测能力
        验证标准:
            - 无遮挡: ≥ 95%
            - 30% 遮挡: ≥ 90%
            - 50% 遮挡: ≥ 80%
            - 70% 遮挡: ≥ 60%
        """
        target = self._make_target(
            target_type=TargetType.VEHICLE, distance_m=50.0, occlusion=occlusion
        )
        rounds = min(self.config["test_rounds"], 30)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label=f"vehicle-50m-occlusion-{occlusion.value}",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name=f"Occlusion {occlusion.value}",
            attachment_type=allure.attachment_type.JSON,
        )

        threshold_map = {
            OcclusionLevel.NONE: 0.95,
            OcclusionLevel.PARTIAL_30: 0.90,
            OcclusionLevel.PARTIAL_50: 0.80,
            OcclusionLevel.PARTIAL_70: 0.60,
        }
        threshold = threshold_map[occlusion]

        assert result.detection_rate >= threshold, (
            f"Occlusion {occlusion.value} detection rate "
            f"{result.detection_rate * 100:.1f}% below {threshold * 100:.0f}%"
        )

    # ----------------------------------------------------------------
    # 6. 光照条件影响
    # ----------------------------------------------------------------

    @allure.title("光照条件检测 - {light}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("light", [
        LightCondition.DAYLIGHT, LightCondition.DUSK,
        LightCondition.NIGHT, LightCondition.BACKLIGHT,
        LightCondition.TUNNEL_EXIT,
    ], ids=["daylight", "dusk", "night", "backlight", "tunnel_exit"])
    def test_light_condition_detection(self, light: LightCondition):
        """
        测试场景: 不同光照条件的检测能力
        验证标准:
            - 白天: ≥ 95%
            - 黄昏/逆光: ≥ 88%
            - 夜间: ≥ 85%
            - 隧道出入口: ≥ 80%
        """
        target = self._make_target(
            target_type=TargetType.VEHICLE, distance_m=50.0, light=light
        )
        rounds = min(self.config["test_rounds"], 30)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label=f"vehicle-50m-{light.value}",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name=f"Light {light.value}",
            attachment_type=allure.attachment_type.JSON,
        )

        threshold_map = {
            LightCondition.DAYLIGHT: 0.95,
            LightCondition.DUSK: 0.88,
            LightCondition.NIGHT: 0.85,
            LightCondition.BACKLIGHT: 0.88,
            LightCondition.TUNNEL_EXIT: 0.80,
        }
        threshold = threshold_map[light]

        assert result.detection_rate >= threshold, (
            f"Light {light.value}: detection rate "
            f"{result.detection_rate * 100:.1f}% below {threshold * 100:.0f}%"
        )

    # ----------------------------------------------------------------
    # 7. 天气条件影响
    # ----------------------------------------------------------------

    @allure.title("天气条件检测 - {weather}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("weather", [
        WeatherCondition.CLEAR, WeatherCondition.RAIN,
        WeatherCondition.FOG, WeatherCondition.SNOW,
    ], ids=["clear", "rain", "fog", "snow"])
    def test_weather_condition_detection(self, weather: WeatherCondition):
        """
        测试场景: 不同天气条件的检测能力
        验证标准:
            - 晴天: ≥ 95%
            - 雨天: ≥ 88%
            - 雪天: ≥ 82%
            - 雾天: ≥ 75%
        """
        target = self._make_target(
            target_type=TargetType.VEHICLE, distance_m=50.0, weather=weather
        )
        rounds = min(self.config["test_rounds"], 30)

        result = self.engine.run_detection_test(
            target=target,
            rounds=rounds,
            condition_label=f"vehicle-50m-{weather.value}",
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name=f"Weather {weather.value}",
            attachment_type=allure.attachment_type.JSON,
        )

        threshold_map = {
            WeatherCondition.CLEAR: 0.95,
            WeatherCondition.RAIN: 0.88,
            WeatherCondition.SNOW: 0.82,
            WeatherCondition.FOG: 0.75,
        }
        threshold = threshold_map[weather]

        assert result.detection_rate >= threshold, (
            f"Weather {weather.value}: detection rate "
            f"{result.detection_rate * 100:.1f}% below {threshold * 100:.0f}%"
        )

    # ----------------------------------------------------------------
    # 8. 分类准确率
    # ----------------------------------------------------------------

    @allure.title("目标分类准确率测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_classification_accuracy(self):
        """
        测试场景: 对各类目标的分类正确率
        验证标准: 分类准确率 ≥ 95%
        """
        all_results = []
        total_detected = 0
        total_correct = 0

        for t_type in [TargetType.VEHICLE, TargetType.PEDESTRIAN, TargetType.CYCLIST, TargetType.TRUCK]:
            target = self._make_target(target_type=t_type, distance_m=50.0)
            rounds = 30

            result = self.engine.run_detection_test(
                target=target,
                rounds=rounds,
                condition_label=f"classification-{t_type.value}",
            )

            # 统计分类正确数 (classified_type == target_type)
            for det in result.details:
                if det.detected:
                    total_detected += 1
                    if det.classified_type == t_type.value:
                        total_correct += 1

            all_results.append({
                "type": t_type.value,
                "detection_rate": result.detection_rate,
                "classification_accuracy": result.classification_accuracy,
            })

        overall_accuracy = total_correct / total_detected if total_detected > 0 else 0.0

        allure.attach(
            json.dumps({
                "overall_accuracy": round(overall_accuracy, 4),
                "per_type": all_results,
            }, ensure_ascii=False, indent=2),
            name="Classification accuracy",
            attachment_type=allure.attachment_type.JSON,
        )

        assert overall_accuracy >= 0.95, (
            f"Classification accuracy {overall_accuracy * 100:.1f}% below 95%"
        )
        logger.info(f"✓ Classification accuracy passed: {overall_accuracy * 100:.1f}%")

    # ----------------------------------------------------------------
    # 9. 误检率
    # ----------------------------------------------------------------

    @allure.title("误检率测试 (空场景)")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_false_positive_rate(self):
        """
        测试场景: 空场景 (无目标), 检查是否误报
        验证标准: 误检率 ≤ 1%
        """
        rounds = min(self.config["test_rounds"], 100)
        result = self.engine.run_false_positive_test(rounds=rounds)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="False positive result",
            attachment_type=allure.attachment_type.JSON,
        )

        max_fp_rate = 0.01
        assert result.false_positive_rate <= max_fp_rate, (
            f"False positive rate {result.false_positive_rate * 100:.2f}% "
            f"exceeds {max_fp_rate * 100:.0f}%"
        )
        logger.info(
            f"✓ False positive test passed: "
            f"{result.false_positive_count}/{result.total_frames}"
        )

    # ----------------------------------------------------------------
    # 10. 综合条件矩阵
    # ----------------------------------------------------------------

    @allure.title("综合条件检测矩阵测试")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    @pytest.mark.regression
    def test_detection_matrix(self):
        """
        测试场景: 目标类型 × 距离 × 光照 组合矩阵
        目的: 全面评估感知系统的鲁棒性
        """
        types = [TargetType.VEHICLE, TargetType.PEDESTRIAN]
        distances = [30, 80]
        lights = [LightCondition.DAYLIGHT, LightCondition.NIGHT]
        matrix_results = []

        for t_type in types:
            for dist in distances:
                for light in lights:
                    target = self._make_target(
                        target_type=t_type, distance_m=float(dist), light=light
                    )
                    result = self.engine.run_detection_test(
                        target=target,
                        rounds=20,
                        condition_label=f"{t_type.value}-{dist}m-{light.value}",
                    )
                    matrix_results.append(result.to_dict())

        allure.attach(
            json.dumps(matrix_results, ensure_ascii=False, indent=2),
            name="Detection condition matrix",
            attachment_type=allure.attachment_type.JSON,
        )

        # 最低底线: 所有条件 ≥ 70%
        for r in matrix_results:
            assert r["detection_rate"] >= 0.70, (
                f"Condition [{r['condition']}] detection rate "
                f"{r['detection_rate_percent']} below 70% baseline"
            )

        logger.info(f"✓ Matrix test completed: {len(matrix_results)} conditions all passed")
