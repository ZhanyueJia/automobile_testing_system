"""
report_generator.py - 测试报告生成器
支持 HTML / JSON / Allure 多格式报告
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from common.utils.logger import get_logger

logger = get_logger("tools.report")


class ReportGenerator:
    """测试报告生成器"""

    def __init__(self, output_dir: str = "reports"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json_report(self, data: dict[str, Any], filename: str = "") -> str:
        """
        生成 JSON 格式报告

        Args:
            data: 报告数据
            filename: 文件名 (不含扩展名)

        Returns:
            报告文件路径
        """
        if not filename:
            filename = f"report_{int(time.time())}"

        output_path = self._output_dir / "json_reports" / f"{filename}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON 报告已生成: {output_path}")
        return str(output_path)

    def generate_summary(self, results: list[dict]) -> dict:
        """
        汇总多个测试结果

        Args:
            results: 测试结果列表

        Returns:
            汇总数据
        """
        total = len(results)
        passed = sum(1 for r in results if r.get("wakeup_rate", 0) >= 0.95)

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_conditions": total,
            "passed_conditions": passed,
            "failed_conditions": total - passed,
            "overall_pass_rate": f"{passed / total * 100:.1f}%" if total > 0 else "N/A",
            "details": results,
        }