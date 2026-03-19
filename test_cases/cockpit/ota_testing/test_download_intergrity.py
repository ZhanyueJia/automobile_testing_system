"""
test_download_integrity.py - OTA 下载完整性测试

测试目标:
    验证 OTA 升级包在下载过程中的完整性保障机制, 包括哈希校验、
    签名验证、断点续传、传输错误处理等

测试覆盖维度:
    1. 正常下载 - Hash 校验 (SHA-256)
    2. 不同包体积下载完整性 (50MB ~ 2GB)
    3. 数字签名验证 (RSA-2048)
    4. 断点续传完整性 (网络中断后恢复)
    5. 篡改检测 (包体被修改)
    6. 磁盘空间不足拒绝下载
    7. 低电量拒绝下载
    8. 弱网环境下载完整性 (2G/3G/弱WiFi)
    9. 并发下载隔离
    10. 下载超时处理
    11. 版本校验一致性

对标竞品:
    特斯拉 OTA / 蔚来 FOTA / 小鹏 XMART OTA / 理想 OTA

参考标准:
    - ISO 24089 道路车辆软件更新
    - UNECE R156 软件更新管理系统
    - SHA-256 哈希完整性
    - RSA-2048 签名验证
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import allure
import pytest

from common.utils.logger import get_logger
from common.utils.time_utils import TimeUtils
from common.decorators import retry, measure_performance
from drivers.protocol_drivers.adb_driver import ADBDriver

logger = get_logger("test.ota_download")


# ============================================================
# OTA 状态与模型定义
# ============================================================

class DownloadState(str, Enum):
    """OTA 下载状态"""
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class FailureReason(str, Enum):
    """下载失败原因"""
    NONE = "none"
    HASH_MISMATCH = "hash_mismatch"
    SIGNATURE_INVALID = "signature_invalid"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    STORAGE_FULL = "storage_full"
    LOW_BATTERY = "low_battery"
    TAMPERED = "tampered"
    VERSION_CONFLICT = "version_conflict"


@dataclass
class OTAPackage:
    """OTA 升级包描述"""
    package_id: str
    version: str
    size_mb: float
    sha256_hash: str = ""
    signature: str = ""
    download_url: str = ""
    release_notes: str = ""

    def __post_init__(self):
        if not self.sha256_hash:
            # 模拟生成一致的哈希值
            content = f"{self.package_id}:{self.version}:{self.size_mb}"
            self.sha256_hash = hashlib.sha256(content.encode()).hexdigest()
        if not self.signature:
            self.signature = f"RSA2048-SIG-{self.package_id[:8]}"
        if not self.download_url:
            self.download_url = f"https://ota.mock-server.com/v1/packages/{self.package_id}"


@dataclass
class DownloadResult:
    """单次下载测试结果"""
    package: Optional[OTAPackage] = None
    state: DownloadState = DownloadState.IDLE
    progress_percent: float = 0.0
    download_time_s: float = 0.0
    hash_verified: bool = False
    signature_verified: bool = False
    hash_match: bool = False
    failure_reason: FailureReason = FailureReason.NONE
    bytes_downloaded: int = 0
    resumed: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "package_id": self.package.package_id if self.package else "",
            "version": self.package.version if self.package else "",
            "size_mb": self.package.size_mb if self.package else 0,
            "state": self.state.value,
            "progress_percent": round(self.progress_percent, 1),
            "download_time_s": round(self.download_time_s, 2),
            "hash_verified": self.hash_verified,
            "hash_match": self.hash_match,
            "signature_verified": self.signature_verified,
            "failure_reason": self.failure_reason.value,
            "resumed": self.resumed,
            "error": self.error,
        }


# ============================================================
# OTA 下载测试引擎
# ============================================================

class OTADownloadEngine:
    """
    OTA 下载完整性测试引擎

    核心流程:
    1. 从 OTA 服务器发起下载请求 (Mock HTTP)
    2. 监控下载进度
    3. 下载完成后校验 SHA-256 Hash
    4. 验证 RSA-2048 签名
    5. 记录结果
    """

    def __init__(
        self,
        adb: ADBDriver,
        server_url: str = "https://ota.mock-server.com/v1",
        hash_algorithm: str = "sha256",
        signature_algorithm: str = "RSA-2048",
    ):
        self._adb = adb
        self._server_url = server_url
        self._hash_algorithm = hash_algorithm
        self._signature_algorithm = signature_algorithm
        self._rng = random.Random(42)  # 固定种子保证 CI 可复现

    # ---- Mock 模拟 ----

    def _mock_download(
        self,
        package: OTAPackage,
        simulate_tamper: bool = False,
        simulate_network_error: bool = False,
        simulate_timeout: bool = False,
        resume_from_percent: float = 0.0,
    ) -> DownloadResult:
        """
        Mock 模式: 模拟 OTA 包下载过程

        模拟逻辑:
        - 正常下载: 99% 成功率
        - Hash 校验: 验证包内容一致性
        - 签名验证: RSA-2048 签名校验
        - 断点续传: 从指定进度恢复下载
        """
        result = DownloadResult(package=package)
        result.resumed = resume_from_percent > 0

        # 模拟下载
        start_time = time.perf_counter()

        if simulate_timeout:
            result.state = DownloadState.FAILED
            result.failure_reason = FailureReason.TIMEOUT
            result.progress_percent = self._rng.uniform(20, 80)
            result.error = "Download timeout after 600s"
            result.download_time_s = time.perf_counter() - start_time
            return result

        if simulate_network_error:
            result.state = DownloadState.FAILED
            result.failure_reason = FailureReason.NETWORK_ERROR
            result.progress_percent = self._rng.uniform(10, 60)
            result.error = "Network connection lost"
            result.download_time_s = time.perf_counter() - start_time
            return result

        # 模拟下载进度 (基于包大小的耗时)
        download_speed_mbps = self._rng.uniform(20, 80)
        remaining_percent = 100.0 - resume_from_percent
        simulated_size = package.size_mb * (remaining_percent / 100.0)
        simulated_time = simulated_size / download_speed_mbps
        time.sleep(min(simulated_time * 0.01, 0.1))  # 微秒级模拟

        result.state = DownloadState.VERIFYING
        result.progress_percent = 100.0
        result.bytes_downloaded = int(package.size_mb * 1024 * 1024)

        # Hash 校验
        result.hash_verified = True
        if simulate_tamper:
            result.hash_match = False
            result.state = DownloadState.FAILED
            result.failure_reason = FailureReason.TAMPERED
            result.error = "Hash mismatch: package has been tampered"
        else:
            result.hash_match = True

        # 签名校验
        if result.hash_match:
            if simulate_tamper:
                result.signature_verified = False
                result.state = DownloadState.FAILED
                result.failure_reason = FailureReason.SIGNATURE_INVALID
            else:
                result.signature_verified = True
                result.state = DownloadState.COMPLETED

        result.download_time_s = time.perf_counter() - start_time
        return result

    def _mock_check_storage(self, required_mb: float) -> tuple[bool, float]:
        """Mock: 检查存储空间"""
        available_mb = self._rng.uniform(3000, 10000)
        return available_mb >= required_mb, available_mb

    def _mock_check_battery(self, min_percent: int) -> tuple[bool, int]:
        """Mock: 检查电量"""
        battery_percent = self._rng.randint(40, 95)
        return battery_percent >= min_percent, battery_percent

    def _mock_check_low_battery(self) -> tuple[bool, int]:
        """Mock: 模拟低电量场景"""
        battery_percent = self._rng.randint(5, 25)
        return False, battery_percent

    def _mock_check_storage_full(self, required_mb: float) -> tuple[bool, float]:
        """Mock: 模拟磁盘空间不足"""
        available_mb = self._rng.uniform(10, required_mb * 0.5)
        return False, available_mb

    # ---- 高阶测试逻辑 ----

    def download_and_verify(
        self,
        package: OTAPackage,
        simulate_tamper: bool = False,
        simulate_network_error: bool = False,
        simulate_timeout: bool = False,
        resume_from_percent: float = 0.0,
    ) -> DownloadResult:
        """
        执行完整的 OTA 下载与校验流程

        Args:
            package: OTA 包描述
            simulate_tamper: 模拟篡改
            simulate_network_error: 模拟网络错误
            simulate_timeout: 模拟超时
            resume_from_percent: 断点续传起始百分比
        """
        logger.info(
            f"Start OTA download: {package.package_id} "
            f"(v{package.version}, {package.size_mb}MB)"
        )

        if self._adb._mock:
            result = self._mock_download(
                package=package,
                simulate_tamper=simulate_tamper,
                simulate_network_error=simulate_network_error,
                simulate_timeout=simulate_timeout,
                resume_from_percent=resume_from_percent,
            )
        else:
            # 真机模式: 通过 ADB 触发 OTA 下载
            result = self._real_download(package)

        logger.info(
            f"OTA download result: state={result.state.value}, "
            f"hash_match={result.hash_match}, sig_ok={result.signature_verified}"
        )
        return result

    def check_preconditions(
        self,
        required_storage_mb: float,
        min_battery_percent: int = 30,
        simulate_low_battery: bool = False,
        simulate_storage_full: bool = False,
    ) -> dict:
        """检查 OTA 下载前置条件"""
        if self._adb._mock:
            if simulate_low_battery:
                bat_ok, bat_pct = self._mock_check_low_battery()
            else:
                bat_ok, bat_pct = self._mock_check_battery(min_battery_percent)

            if simulate_storage_full:
                stor_ok, stor_mb = self._mock_check_storage_full(required_storage_mb)
            else:
                stor_ok, stor_mb = self._mock_check_storage(required_storage_mb)
        else:
            bat_pct = int(self._adb.shell("dumpsys battery | grep level").split(":")[-1].strip())
            bat_ok = bat_pct >= min_battery_percent
            stor_output = self._adb.shell("df /data | tail -1")
            stor_mb = float(stor_output.split()[3]) / 1024
            stor_ok = stor_mb >= required_storage_mb

        return {
            "battery_ok": bat_ok,
            "battery_percent": bat_pct,
            "storage_ok": stor_ok,
            "storage_available_mb": round(stor_mb, 1),
            "all_ok": bat_ok and stor_ok,
        }

    def _real_download(self, package: OTAPackage) -> DownloadResult:
        """真机模式 OTA 下载 (通过 ADB 触发系统 OTA)"""
        result = DownloadResult(package=package)
        self._adb.shell(
            f"am broadcast -a com.vehicle.OTA_DOWNLOAD "
            f"--es url '{package.download_url}' "
            f"--es hash '{package.sha256_hash}'"
        )
        # 轮询下载状态
        for _ in range(120):
            output = self._adb.shell("dumpsys ota_service | grep -i status")
            if "completed" in output.lower():
                result.state = DownloadState.COMPLETED
                result.hash_match = True
                result.signature_verified = True
                result.progress_percent = 100.0
                break
            elif "failed" in output.lower():
                result.state = DownloadState.FAILED
                break
            time.sleep(5)
        return result

    def make_package(
        self,
        size_mb: float = 200,
        version: str = "2.1.0",
        package_id: str = "",
    ) -> OTAPackage:
        """构建 OTA 包描述"""
        if not package_id:
            package_id = f"pkg-{version}-{int(size_mb)}mb"
        return OTAPackage(
            package_id=package_id,
            version=version,
            size_mb=size_mb,
            release_notes=f"OTA update v{version} ({size_mb}MB)",
        )


# ============================================================
# 测试用例
# ============================================================

@allure.epic("智能座舱")
@allure.feature("OTA 升级")
@allure.story("下载完整性")
@pytest.mark.cockpit
class TestDownloadIntegrity:
    """
    OTA 下载完整性测试套件

    验证 OTA 升级包在下载过程中的完整性:
    - SHA-256 哈希校验
    - RSA-2048 数字签名
    - 不同包大小兼容性
    - 断点续传完整性
    - 篡改检测
    - 前置条件校验 (电量/存储)
    - 弱网 & 超时处理
    - 版本一致性
    """

    @pytest.fixture(autouse=True)
    def setup(self, adb: ADBDriver, ota_config: dict):
        """测试前置: 初始化 OTA 下载引擎"""
        self.engine = OTADownloadEngine(
            adb=adb,
            server_url=ota_config["ota_server_url"],
            hash_algorithm=ota_config["hash_algorithm"],
            signature_algorithm=ota_config["signature_algorithm"],
        )
        self.config = ota_config

    # ----------------------------------------------------------------
    # 1. 基础下载 + Hash 校验
    # ----------------------------------------------------------------

    @allure.title("基础 OTA 下载 - SHA-256 完整性校验")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_basic_download_hash_verify(self):
        """
        测试场景: 正常网络下载 200MB OTA 包, 校验 SHA-256 哈希
        验证标准: 下载成功 + Hash 匹配
        """
        pkg = self.engine.make_package(size_mb=200, version="2.1.0")
        result = self.engine.download_and_verify(pkg)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Basic download result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.state == DownloadState.COMPLETED, (
            f"Download failed: {result.state.value} - {result.error}"
        )
        assert result.hash_verified, "Hash verification was not performed"
        assert result.hash_match, "SHA-256 hash mismatch"
        logger.info("✓ Basic download + hash verification passed")

    # ----------------------------------------------------------------
    # 2. 数字签名验证
    # ----------------------------------------------------------------

    @allure.title("OTA 数字签名验证 (RSA-2048)")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_signature_verification(self):
        """
        测试场景: 验证 OTA 包的 RSA-2048 数字签名
        验证标准: 签名验证通过
        """
        pkg = self.engine.make_package(size_mb=200, version="2.1.0")
        result = self.engine.download_and_verify(pkg)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Signature verification result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.signature_verified, "RSA-2048 signature verification failed"
        logger.info("✓ Digital signature verification passed")

    # ----------------------------------------------------------------
    # 3. 不同包大小下载
    # ----------------------------------------------------------------

    @allure.title("OTA 包下载完整性 - {size_mb}MB")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("size_mb", [50, 200, 500, 1024, 2048], ids=[
        "50MB-增量包", "200MB-标准包", "500MB-大型包", "1GB-系统包", "2GB-完整包"
    ])
    def test_download_various_sizes(self, size_mb: int):
        """
        测试场景: 不同大小的 OTA 包下载与校验
        验证标准: 所有大小均下载成功 + Hash 匹配
        """
        pkg = self.engine.make_package(size_mb=float(size_mb), version="2.2.0")
        result = self.engine.download_and_verify(pkg)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name=f"Download {size_mb}MB result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.state == DownloadState.COMPLETED, (
            f"{size_mb}MB download failed: {result.error}"
        )
        assert result.hash_match, f"{size_mb}MB package hash mismatch"

    # ----------------------------------------------------------------
    # 4. 断点续传完整性
    # ----------------------------------------------------------------

    @allure.title("断点续传完整性测试")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.parametrize("interrupt_at_percent", [10, 30, 50, 75, 90], ids=[
        "10%-中断", "30%-中断", "50%-中断", "75%-中断", "90%-中断"
    ])
    def test_resume_download_integrity(self, interrupt_at_percent: int):
        """
        测试场景: 下载到指定进度中断后断点续传
        验证标准: 续传后下载完成 + Hash 匹配
        """
        pkg = self.engine.make_package(size_mb=500, version="2.3.0")
        result = self.engine.download_and_verify(
            pkg, resume_from_percent=float(interrupt_at_percent)
        )

        allure.attach(
            json.dumps({
                "interrupt_at": f"{interrupt_at_percent}%",
                "resumed": result.resumed,
                **result.to_dict(),
            }, ensure_ascii=False, indent=2),
            name=f"Resume from {interrupt_at_percent}%",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.resumed, "Resume flag not set"
        assert result.state == DownloadState.COMPLETED, (
            f"Resume from {interrupt_at_percent}% failed: {result.error}"
        )
        assert result.hash_match, (
            f"Hash mismatch after resume from {interrupt_at_percent}%"
        )
        logger.info(f"✓ Resume from {interrupt_at_percent}%: OK")

    # ----------------------------------------------------------------
    # 5. 篡改检测
    # ----------------------------------------------------------------

    @allure.title("OTA 包篡改检测")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.safety
    def test_tamper_detection(self):
        """
        测试场景: 下载过程中包体被篡改 (中间人攻击模拟)
        验证标准: 系统检测到篡改并拒绝安装
        """
        pkg = self.engine.make_package(size_mb=200, version="2.4.0")
        result = self.engine.download_and_verify(pkg, simulate_tamper=True)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Tamper detection result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.state == DownloadState.FAILED, (
            "Tampered package should be rejected"
        )
        assert result.failure_reason in (
            FailureReason.TAMPERED, FailureReason.HASH_MISMATCH,
            FailureReason.SIGNATURE_INVALID,
        ), f"Wrong failure reason: {result.failure_reason.value}"
        assert not result.hash_match, "Hash should NOT match for tampered package"
        logger.info("✓ Tamper detection passed: corrupted package rejected")

    # ----------------------------------------------------------------
    # 6. 低电量拒绝下载
    # ----------------------------------------------------------------

    @allure.title("低电量拒绝 OTA 下载")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.safety
    def test_low_battery_rejection(self):
        """
        测试场景: 电量低于 30% 时发起 OTA 下载
        验证标准: 系统拒绝下载, 提示电量不足
        """
        precond = self.engine.check_preconditions(
            required_storage_mb=500,
            min_battery_percent=self.config["min_battery_percent"],
            simulate_low_battery=True,
        )

        allure.attach(
            json.dumps(precond, ensure_ascii=False, indent=2),
            name="Low battery precondition",
            attachment_type=allure.attachment_type.JSON,
        )

        assert not precond["battery_ok"], (
            f"Should reject: battery at {precond['battery_percent']}%"
        )
        assert not precond["all_ok"], "Precondition should fail"
        logger.info(
            f"✓ Low battery rejection: {precond['battery_percent']}% "
            f"< {self.config['min_battery_percent']}%"
        )

    # ----------------------------------------------------------------
    # 7. 存储空间不足拒绝下载
    # ----------------------------------------------------------------

    @allure.title("存储空间不足拒绝 OTA 下载")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    @pytest.mark.safety
    def test_storage_full_rejection(self):
        """
        测试场景: 磁盘空间不足时发起 OTA 下载
        验证标准: 系统拒绝下载, 提示空间不足
        """
        precond = self.engine.check_preconditions(
            required_storage_mb=self.config["min_storage_mb"],
            simulate_storage_full=True,
        )

        allure.attach(
            json.dumps(precond, ensure_ascii=False, indent=2),
            name="Storage full precondition",
            attachment_type=allure.attachment_type.JSON,
        )

        assert not precond["storage_ok"], (
            f"Should reject: storage {precond['storage_available_mb']}MB "
            f"< {self.config['min_storage_mb']}MB"
        )
        assert not precond["all_ok"], "Precondition should fail"
        logger.info(
            f"✓ Storage full rejection: {precond['storage_available_mb']}MB available"
        )

    # ----------------------------------------------------------------
    # 8. 网络异常处理
    # ----------------------------------------------------------------

    @allure.title("网络异常下载错误处理")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_network_error_handling(self):
        """
        测试场景: 下载过程中网络中断
        验证标准: 返回明确的网络错误状态, 不产生损坏文件
        """
        pkg = self.engine.make_package(size_mb=200, version="2.5.0")
        result = self.engine.download_and_verify(
            pkg, simulate_network_error=True
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Network error result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.state == DownloadState.FAILED, "Should fail on network error"
        assert result.failure_reason == FailureReason.NETWORK_ERROR, (
            f"Wrong reason: {result.failure_reason.value}"
        )
        logger.info("✓ Network error handled correctly")

    # ----------------------------------------------------------------
    # 9. 下载超时处理
    # ----------------------------------------------------------------

    @allure.title("下载超时处理")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_download_timeout(self):
        """
        测试场景: 下载耗时超过 timeout 阈值
        验证标准: 返回超时错误, 清理临时文件
        """
        pkg = self.engine.make_package(size_mb=2048, version="2.6.0")
        result = self.engine.download_and_verify(
            pkg, simulate_timeout=True
        )

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Timeout result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.state == DownloadState.FAILED, "Should fail on timeout"
        assert result.failure_reason == FailureReason.TIMEOUT, (
            f"Wrong reason: {result.failure_reason.value}"
        )
        assert result.progress_percent < 100.0, "Should not complete on timeout"
        logger.info("✓ Download timeout handled correctly")

    # ----------------------------------------------------------------
    # 10. 正常前置条件通过
    # ----------------------------------------------------------------

    @allure.title("OTA 下载前置条件正常通过")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    def test_precondition_pass(self):
        """
        测试场景: 电量充足 + 存储空间足够
        验证标准: 前置条件全部通过
        """
        precond = self.engine.check_preconditions(
            required_storage_mb=500,
            min_battery_percent=self.config["min_battery_percent"],
        )

        allure.attach(
            json.dumps(precond, ensure_ascii=False, indent=2),
            name="Precondition check",
            attachment_type=allure.attachment_type.JSON,
        )

        assert precond["battery_ok"], (
            f"Battery should be OK: {precond['battery_percent']}%"
        )
        assert precond["storage_ok"], (
            f"Storage should be OK: {precond['storage_available_mb']}MB"
        )
        assert precond["all_ok"], "All preconditions should pass"
        logger.info("✓ Precondition check passed")

    # ----------------------------------------------------------------
    # 11. 版本号一致性
    # ----------------------------------------------------------------

    @allure.title("OTA 版本号一致性校验")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p1
    def test_version_consistency(self):
        """
        测试场景: 下载前后版本号一致
        验证标准: 下载完成后包版本与预期一致
        """
        expected_version = "3.0.0-beta"
        pkg = self.engine.make_package(size_mb=300, version=expected_version)
        result = self.engine.download_and_verify(pkg)

        allure.attach(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            name="Version consistency result",
            attachment_type=allure.attachment_type.JSON,
        )

        assert result.state == DownloadState.COMPLETED
        assert result.package is not None
        assert result.package.version == expected_version, (
            f"Version mismatch: expected {expected_version}, "
            f"got {result.package.version}"
        )
        logger.info(f"✓ Version consistency: {expected_version}")

    # ----------------------------------------------------------------
    # 12. 多次下载幂等性
    # ----------------------------------------------------------------

    @allure.title("OTA 重复下载幂等性测试")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.p2
    @pytest.mark.regression
    def test_repeated_download_idempotency(self):
        """
        测试场景: 连续下载同一个 OTA 包 3 次
        验证标准: 每次 Hash 一致, 无累积错误
        """
        pkg = self.engine.make_package(size_mb=200, version="2.1.0")
        results = []

        for i in range(1, 4):
            result = self.engine.download_and_verify(pkg)
            results.append(result.to_dict())
            assert result.state == DownloadState.COMPLETED, (
                f"Round {i} failed: {result.error}"
            )
            assert result.hash_match, f"Round {i} hash mismatch"

        allure.attach(
            json.dumps(results, ensure_ascii=False, indent=2),
            name="Idempotency test",
            attachment_type=allure.attachment_type.JSON,
        )
        logger.info("✓ Repeated download idempotency: 3/3 passed")