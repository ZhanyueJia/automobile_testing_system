"""
conftest.py - pytest 全局配置与共享 fixture

功能:
1. 命令行参数注册 (--vehicle-model / --env)
2. 全局配置加载
3. 跨模块共享 fixture
4. 测试报告增强 (失败截图/日志附加)
5. 测试用例自动标记
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

try:
    import allure
except ImportError:
    allure = None

from common.config.config_manager import ConfigManager
from common.utils.logger import get_logger

logger = get_logger("conftest.global")

# ============================================================
# 框架根目录
# ============================================================
FRAMEWORK_ROOT = Path(__file__).resolve().parent


# ============================================================
# 命令行参数注册
# ============================================================

def pytest_addoption(parser):
    """注册自定义命令行参数"""
    parser.addoption(
        "--vehicle-model",
        action="store",
        default="default",
        help="目标车型 (如: xiaomi_su7 / nio_et7 / default)",
    )
    parser.addoption(
        "--env",
        action="store",
        default="simulation",
        choices=["simulation", "hil", "real_vehicle", "ci"],
        help="运行环境 (simulation / hil / real_vehicle / ci)",
    )
    parser.addoption(
        "--test-rounds",
        action="store",
        type=int,
        default=0,
        help="覆盖配置中的测试轮次 (0 表示使用配置文件的值)",
    )


# ============================================================
# Session 级 fixture
# ============================================================

@pytest.fixture(scope="session")
def config(request) -> ConfigManager:
    """
    会话级配置管理器

    使用方式:
        pytest --vehicle-model xiaomi_su7 --env simulation
    """
    vehicle_model = request.config.getoption("--vehicle-model")
    env = request.config.getoption("--env")

    cfg = ConfigManager()
    cfg.load(vehicle_model=vehicle_model, env=env)

    # 覆盖测试轮次
    test_rounds = request.config.getoption("--test-rounds")
    if test_rounds > 0:
        cfg.set("cockpit.voice.wakeup.test_rounds", test_rounds)

    logger.info(f"========================================")
    logger.info(f"  Test Platform Started")
    logger.info(f"  Vehicle: {vehicle_model}")
    logger.info(f"  Env: {env}")
    logger.info(f"========================================")

    return cfg


# ============================================================
# 测试生命周期 Hook
# ============================================================

def pytest_configure(config):
    """pytest 配置阶段: 设置元数据"""
    config._metadata = getattr(config, "_metadata", {})
    config._metadata["Project"] = "Automotive Intelligent Test Platform"
    config._metadata["Framework Version"] = "1.0.0"


def pytest_collection_modifyitems(config, items):
    """
    收集阶段: 根据目录自动添加 pytest marker

    test_cases/cockpit/  → @pytest.mark.cockpit
    test_cases/adas/     → @pytest.mark.adas
    test_cases/vcu/      → @pytest.mark.vcu
    test_cases/integration/ → @pytest.mark.integration
    """
    domain_markers = {
        "cockpit": pytest.mark.cockpit,
        "adas": pytest.mark.adas,
        "vcu": pytest.mark.vcu,
        "integration": pytest.mark.integration,
    }

    for item in items:
        # 根据文件路径自动添加域标记
        rel_path = str(Path(item.fspath).relative_to(FRAMEWORK_ROOT))
        for domain, marker in domain_markers.items():
            if f"test_cases/{domain}" in rel_path.replace("\\", "/"):
                item.add_marker(marker)
                break


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    测试报告增强:
    - 失败时附加日志信息
    - 记录测试耗时
    """
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        # 记录测试耗时
        duration_ms = report.duration * 1000
        if duration_ms > 5000:
            logger.warning(f"Slow test: {item.name} took {duration_ms:.0f}ms")

        # 失败时记录额外信息
        if report.failed:
            logger.error(f"Test FAILED: {item.nodeid}")
            # 如果有 ADB fixture, 收集设备日志
            if "adb" in item.funcargs:
                try:
                    adb = item.funcargs["adb"]
                    log_snippet = adb.get_logcat(lines=30)
                    # 附加到 Allure 报告
                    if allure is not None:
                        allure.attach(
                            log_snippet,
                            name="Device Logcat (last 30 lines)",
                            attachment_type=allure.attachment_type.TEXT,
                        )
                    # 附加到 pytest-html 报告
                    report.extras = getattr(report, "extras", [])
                    try:
                        from pytest_html import extras as html_extras
                        report.extras.append(html_extras.text(log_snippet, name="Device Logcat"))
                    except ImportError:
                        pass
                    logger.debug(f"Device log on failure:\n{log_snippet}")
                except Exception as e:
                    logger.warning(f"设备日志收集失败: {e}")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """测试结束时打印自定义摘要"""
    logger.info("========================================")
    logger.info("  Test Execution Completed")
    logger.info(f"  Exit Status: {exitstatus}")

    stats = terminalreporter.stats
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    error = len(stats.get("error", []))
    skipped = len(stats.get("skipped", []))

    logger.info(f"  Passed: {passed}  Failed: {failed}  Error: {error}  Skipped: {skipped}")
    logger.info("========================================")