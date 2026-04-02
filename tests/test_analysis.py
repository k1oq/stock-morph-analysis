#!/usr/bin/env python3
"""
分析逻辑单元测试。
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from morph_analyzer import (
    analyze_volume_price,
    build_analysis_result,
    calc_support_resistance,
    determine_ma_arrangement,
    generate_report,
)


def sample_realtime() -> dict:
    return {
        "code": "600867",
        "name": "通化东宝",
        "price": 9.75,
        "prev_close": 9.59,
        "open": 9.63,
        "high": 9.86,
        "low": 9.51,
        "change_amount": 0.16,
        "change": 1.67,
        "volume_hands": 1043943.0,
        "volume_shares": 104394300.0,
        "amount_wan_yuan": 101179.01,
        "amount_yi_yuan": 10.12,
        "timestamp": "2026-04-02 16:14:28",
    }


class AnalysisTests(unittest.TestCase):
    def test_analyze_volume_price_classifies_bullish_volume(self) -> None:
        result = analyze_volume_price(1.5, 2.1)
        self.assertEqual(result["relation"], "量增价升")
        self.assertGreater(result["score"], 0)

    def test_determine_ma_arrangement_bullish(self) -> None:
        arrangement = determine_ma_arrangement(
            11.2,
            {"ma5": 10.8, "ma10": 10.5, "ma20": 10.1, "ma60": 9.8},
        )
        self.assertEqual(arrangement["name"], "多头排列")

    def test_calc_support_resistance_prefers_nearest_levels(self) -> None:
        realtime = sample_realtime()
        history_rows = [
            {"day": f"2026-03-{day:02d}", "open": 9.0, "high": 9.9 + day * 0.01, "low": 8.5, "close": 9.1, "volume_shares": 1.0, "volume_hands": 0.01}
            for day in range(1, 21)
        ]
        moving_averages = {
            "ma5": {"value": 9.45, "distance_percent": 3.13},
            "ma10": {"value": 9.20, "distance_percent": 5.98},
            "ma20": {"value": 8.95, "distance_percent": 8.94},
            "ma60": {"value": 8.70, "distance_percent": 12.07},
        }

        result = calc_support_resistance(realtime, history_rows, moving_averages)
        self.assertEqual(result["resistance"][0]["price"], 9.86)
        self.assertEqual(result["support"][0]["price"], 9.51)

    @patch("morph_analyzer.get_history_kline")
    @patch("morph_analyzer.get_realtime_data")
    def test_build_analysis_result_degrades_when_history_fails(self, mock_realtime, mock_history) -> None:
        mock_realtime.return_value = sample_realtime()
        mock_history.side_effect = RuntimeError("history unavailable")

        result = build_analysis_result("600867")

        self.assertEqual(result["data_status"]["history"], "degraded")
        self.assertEqual(result["data_status"]["indicators"], "degraded")
        self.assertTrue(result["warnings"])
        self.assertIsNone(result["moving_averages"]["ma5"]["value"])
        self.assertEqual(result["volume_price"]["relation"], "不可用")

    @patch("morph_analyzer.get_history_kline")
    @patch("morph_analyzer.get_realtime_data")
    def test_generate_report_contains_key_sections(self, mock_realtime, mock_history) -> None:
        mock_realtime.return_value = sample_realtime()
        mock_history.return_value = [
            {
                "day": f"2026-03-{day:02d}",
                "open": 8.5 + day * 0.01,
                "high": 8.8 + day * 0.02,
                "low": 8.3 + day * 0.01,
                "close": 8.6 + day * 0.02,
                "volume_shares": 80000000 + day * 10000,
                "volume_hands": (80000000 + day * 10000) / 100,
            }
            for day in range(1, 32)
        ]

        result = build_analysis_result("600867")
        report = generate_report(result, detailed=True)

        self.assertIn("【实时行情】", report)
        self.assertIn("【技术指标】", report)
        self.assertIn("【技术评分】", report)
        self.assertIn("【支撑压力】", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
