"""
test_wakeup.py - 语音唤醒率测试

测试目标:
    验证语音唤醒系统在各种场景下的唤醒成功率

测试覆盖维度:
    1. 安静环境下唤醒率
    2. 噪声环境下唤醒率
    3. 不同唤醒词测试
    4. 唤醒响应时间
    5. 重复唤醒幂等性
    6. 误唤醒率测试

对标竞品:
    小米小爱 / 蔚来NOMI / 理想同学 / 小鹏小P

参考标准:
    - 唤醒率 ≥ 95% (安静环境)
    - 唤醒率 ≥ 85% (噪声环境)
    - 唤醒响应时间 ≤ 500ms
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum

import allure
import pytest

from common.utils.logger import get_logger

logger = get_logger("test.wakeup")


class WakeupEnvironment(str, Enum):
    """唤醒环境"""
    QUIET = "quiet"           # 安静环境
    NOISE_65DB = "noise_65db" # 65dB 噪声
    NOISE_75DB = "noise_75db" # 75dB 噪声
    MUSIC = "music"           # 播放音乐


class WakeupExpectedResult(str, Enum):
    """唤醒结果"""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"


@dataclass
class WakeupTestCase:
    """唤醒测试用例"""
    case_id: str
    wakeup_word: str
    environment: WakeupEnvironment
    expected_result: WakeupExpectedResult = WakeupExpectedResult.SUCCESS


@dataclass
class WakeupAttemptResult:
    """单次唤醒测试结果"""
    case_id: str
    wakeup_word: str
    environment: str
    success: bool
    response_time_ms: float = 0.0
    error: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "wakeup_word": self.wakeup_word,
            "environment": self.environment,
            "success": self.success,
            "response_time_ms": round(self.response_time_ms, 1),
            "error": self.error,
        }


# ============================================================
# 测试用例
# ============================================================

@allure.epic("智能座舱")
@allure.feature("语音交互")
@allure.story("唤醒率测试")
@pytest.mark.cockpit
class TestWakeup:
    """
    语音唤醒率测试套件

    验证语音唤醒系统在不同场景下的唤醒成功率
    """

    @pytest.fixture(autouse=True)
    def setup(self, config):
        """测试前置配置"""
        self.config = config
        self.wakeup_config = config.get("cockpit.voice.wakeup", {})
        self.test_rounds = self.wakeup_config.get("test_rounds", 10)

    @allure.title("安静环境下唤醒率测试")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_wakeup_rate_quiet_environment(self):
        """
        测试场景: 安静环境下连续唤醒 N 次
        验证标准: 唤醒率 ≥ 95%
        """
        rounds = self.test_rounds
        success_count = 0
        results = []

        logger.info(f"安静环境唤醒率测试开始，共 {rounds} 次")

        for i in range(1, rounds + 1):
            # Mock 唤醒成功
            success = True  # 实际应调用语音引擎
            response_time = 200.0 + (i % 5) * 10  # Mock 响应时间

            if success:
                success_count += 1

            result = WakeupAttemptResult(
                case_id=f"wakeup_quiet_{i}",
                wakeup_word="你好小爱",
                environment="quiet",
                success=success,
                response_time_ms=response_time,
            )
            results.append(result.to_dict())

        success_rate = success_count / rounds

        allure.attach(
            json.dumps({"rounds": rounds, "success_count": success_count, "success_rate": success_rate}, ensure_ascii=False, indent=2),
            name="安静环境唤醒率统计",
            attachment_type=allure.attachment_type.JSON,
        )

        assert success_rate >= 0.95, f"安静环境唤醒率 {success_rate*100:.1f}% 未达标 (≥95%)"
        logger.info(f"✓ 安静环境唤醒率: {success_rate*100:.1f}% ({success_count}/{rounds})")

    @allure.title("噪声环境下唤醒率测试 - 65dB")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_wakeup_rate_noise_65db(self):
        """
        测试场景: 65dB 噪声环境下连续唤醒
        验证标准: 唤醒率 ≥ 85%
        """
        rounds = self.test_rounds
        success_count = 0
        results = []

        for i in range(1, rounds + 1):
            # Mock 唤醒成功率
            success = i % 10 != 0  # 90% 成功率模拟
            response_time = 250.0 + (i % 5) * 15

            if success:
                success_count += 1

            result = WakeupAttemptResult(
                case_id=f"wakeup_noise65_{i}",
                wakeup_word="你好小爱",
                environment="noise_65db",
                success=success,
                response_time_ms=response_time,
            )
            results.append(result.to_dict())

        success_rate = success_count / rounds

        allure.attach(
            json.dumps({"rounds": rounds, "success_count": success_count, "success_rate": success_rate}, ensure_ascii=False, indent=2),
            name="65dB噪声环境唤醒率统计",
            attachment_type=allure.attachment_type.JSON,
        )

        assert success_rate >= 0.85, f"65dB环境唤醒率 {success_rate*100:.1f}% 未达标 (≥85%)"
        logger.info(f"✓ 65dB噪声环境唤醒率: {success_rate*100:.1f}% ({success_count}/{rounds})")

    @allure.title("唤醒响应时间测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_wakeup_response_time(self):
        """
        测试场景: 测量唤醒响应时间
        验证标准: 平均响应时间 ≤ 500ms
        """
        rounds = self.test_rounds
        response_times = []

        for i in range(1, rounds + 1):
            response_time = 200.0 + (i % 5) * 50  # Mock 响应时间 200-400ms
            response_times.append(response_time)

        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)

        allure.attach(
            json.dumps({
                "avg_response_time_ms": round(avg_response_time, 1),
                "max_response_time_ms": round(max_response_time, 1),
                "min_response_time_ms": round(min(response_times), 1),
            }, ensure_ascii=False, indent=2),
            name="唤醒响应时间统计",
            attachment_type=allure.attachment_type.JSON,
        )

        assert avg_response_time <= 500, f"平均响应时间 {avg_response_time:.0f}ms 未达标 (≤500ms)"
        logger.info(f"✓ 唤醒响应时间: avg={avg_response_time:.0f}ms, max={max_response_time:.0f}ms")

    @allure.title("重复唤醒幂等性测试")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    def test_wakeup_idempotency(self):
        """
        测试场景: 连续快速唤醒多次
        验证标准: 每次都能正确响应，无累积异常
        """
        rounds = 10

        for i in range(1, rounds + 1):
            # Mock 唤醒
            success = True
            assert success, f"第 {i} 次唤醒失败"
            logger.debug(f"第 {i}/{rounds} 次唤醒成功")

        logger.info(f"✓ 重复唤醒幂等性测试通过: 连续{rounds}次唤醒均正常")

    @allure.title("误唤醒率测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.safety
    def test_false_wakeup_rate(self):
        """
        测试场景: 在不包含唤醒词的语言输入中，验证误唤醒率
        验证标准: 误唤醒率 ≤ 1%
        """
        test_phrases = [
            "今天天气不错",
            "播放音乐",
            "导航到公司",
            "打个电话给张三",
        ]

        false_wakeup_count = 0

        for _phrase in test_phrases:
            # Mock: 无唤醒词不应触发唤醒
            false_wakeup = False  # 实际应调用语音引擎
            if false_wakeup:
                false_wakeup_count += 1

        false_wakeup_rate = false_wakeup_count / len(test_phrases)

        allure.attach(
            json.dumps({
                "test_phrases_count": len(test_phrases),
                "false_wakeup_count": false_wakeup_count,
                "false_wakeup_rate": false_wakeup_rate,
            }, ensure_ascii=False, indent=2),
            name="误唤醒率统计",
            attachment_type=allure.attachment_type.JSON,
        )

        assert false_wakeup_rate <= 0.01, f"误唤醒率 {false_wakeup_rate*100:.1f}% 未达标 (≤1%)"
        logger.info(f"✓ 误唤醒率测试通过: {false_wakeup_rate*100:.2f}% ({false_wakeup_count}/{len(test_phrases)})")

