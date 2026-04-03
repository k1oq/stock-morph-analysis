#!/usr/bin/env python3
"""
单股分析组合测试。
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
        "timestamp": "2026-04-03 15:00:00",
    }


def sample_history_rows(count: int = 40) -> list[dict]:
    rows = []
    for day in range(1, count + 1):
        volume_shares = 80000000 + day * 500000
        rows.append(
            {
                "day": f"2026-03-{day:02d}",
                "open": 8.80 + day * 0.03,
                "high": 9.10 + day * 0.03,
                "low": 8.60 + day * 0.03,
                "close": 8.90 + day * 0.03,
                "volume_shares": volume_shares,
                "volume_hands": volume_shares / 100,
            }
        )
    return rows


def sample_market_history_rows(count: int = 80) -> list[dict]:
    rows = []
    for day in range(1, count + 1):
        volume_shares = 70000000 + day * 600000
        amount_yuan = 800000000 + day * 12000000
        rows.append(
            {
                "date": f"2026-02-{day:02d}" if day <= 28 else f"2026-03-{day - 28:02d}",
                "open": 8.70 + day * 0.02,
                "close": 8.85 + day * 0.02,
                "high": 9.05 + day * 0.02,
                "low": 8.55 + day * 0.02,
                "volume_shares": volume_shares,
                "volume_hands": volume_shares / 100,
                "amount_yuan": amount_yuan,
                "amount_wan_yuan": amount_yuan / 10000,
                "amount_yi_yuan": amount_yuan / 100000000,
                "amplitude": 3.5,
                "change_percent": 1.2,
                "change_amount": 0.12,
                "turnover_rate": 2.5 + day * 0.03,
            }
        )
    return rows


def sample_fund_flow_rows(count: int = 8) -> list[dict]:
    rows = []
    for day in range(1, count + 1):
        main_net_inflow_yuan = 30000000 + day * 3000000
        rows.append(
            {
                "date": f"2026-03-{day:02d}",
                "main_net_inflow_yuan": main_net_inflow_yuan,
                "main_net_inflow_yi_yuan": main_net_inflow_yuan / 100000000,
                "small_net_inflow_yuan": -12000000.0,
                "medium_net_inflow_yuan": -5000000.0,
                "large_net_inflow_yuan": 16000000.0,
                "super_large_net_inflow_yuan": 22000000.0,
                "main_net_inflow_ratio": 6.5,
                "small_net_inflow_ratio": -2.4,
                "medium_net_inflow_ratio": -1.2,
                "large_net_inflow_ratio": 2.1,
                "super_large_net_inflow_ratio": 3.4,
                "close": 9.75,
                "change_percent": 1.67,
            }
        )
    return rows


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
            {
                "day": f"2026-03-{day:02d}",
                "open": 9.0,
                "high": 9.9 + day * 0.01,
                "low": 8.5,
                "close": 9.1,
                "volume_shares": 1.0,
                "volume_hands": 0.01,
            }
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

    @patch("morph_analyzer.fetch_individual_fund_flow_history")
    @patch("morph_analyzer.fetch_market_activity_history")
    @patch("morph_analyzer.get_history_kline")
    @patch("morph_analyzer.get_realtime_data")
    def test_build_analysis_result_degrades_when_data_sources_fail(
        self,
        mock_realtime,
        mock_history,
        mock_market_history,
        mock_fund_flow,
    ) -> None:
        mock_realtime.return_value = sample_realtime()
        mock_history.side_effect = RuntimeError("history unavailable")
        mock_market_history.side_effect = RuntimeError("eastmoney unavailable")
        mock_fund_flow.side_effect = RuntimeError("fund flow unavailable")

        result = build_analysis_result("600867")

        self.assertEqual(result["data_status"]["history"], "degraded")
        self.assertEqual(result["data_status"]["indicators"], "degraded")
        self.assertEqual(result["data_status"]["volume_profile"], "degraded")
        self.assertEqual(result["data_status"]["turnover"], "degraded")
        self.assertEqual(result["data_status"]["chip_distribution"], "degraded")
        self.assertEqual(result["data_status"]["fund_flow"], "degraded")
        self.assertGreaterEqual(len(result["warnings"]), 3)
        self.assertIsNone(result["moving_averages"]["ma5"]["value"])
        self.assertFalse(result["volume_profile"]["available"])
        self.assertFalse(result["turnover_analysis"]["available"])
        self.assertFalse(result["chip_distribution"]["available"])
        self.assertFalse(result["fund_flow"]["available"])

    @patch("morph_analyzer.fetch_individual_fund_flow_history")
    @patch("morph_analyzer.fetch_market_activity_history")
    @patch("morph_analyzer.get_history_kline")
    @patch("morph_analyzer.get_realtime_data")
    def test_build_analysis_result_includes_market_extensions(
        self,
        mock_realtime,
        mock_history,
        mock_market_history,
        mock_fund_flow,
    ) -> None:
        mock_realtime.return_value = sample_realtime()
        mock_history.return_value = sample_history_rows()
        mock_market_history.return_value = sample_market_history_rows()
        mock_fund_flow.return_value = sample_fund_flow_rows()

        result = build_analysis_result("600867")

        self.assertEqual(result["data_status"]["history"], "complete")
        self.assertEqual(result["data_status"]["indicators"], "complete")
        self.assertEqual(result["data_status"]["volume_profile"], "complete")
        self.assertEqual(result["data_status"]["turnover"], "complete")
        self.assertEqual(result["data_status"]["chip_distribution"], "complete")
        self.assertEqual(result["data_status"]["fund_flow"], "complete")
        self.assertTrue(result["volume_profile"]["available"])
        self.assertTrue(result["turnover_analysis"]["available"])
        self.assertTrue(result["chip_distribution"]["available"])
        self.assertTrue(result["fund_flow"]["available"])
        self.assertEqual(result["realtime"]["turnover_rate"], result["turnover_analysis"]["latest_turnover_rate"])

    @patch("morph_analyzer.fetch_individual_fund_flow_history")
    @patch("morph_analyzer.fetch_market_activity_history")
    @patch("morph_analyzer.get_history_kline")
    @patch("morph_analyzer.get_realtime_data")
    def test_generate_report_contains_new_sections(
        self,
        mock_realtime,
        mock_history,
        mock_market_history,
        mock_fund_flow,
    ) -> None:
        mock_realtime.return_value = sample_realtime()
        mock_history.return_value = sample_history_rows()
        mock_market_history.return_value = sample_market_history_rows()
        mock_fund_flow.return_value = sample_fund_flow_rows()

        result = build_analysis_result("600867")
        report = generate_report(result, detailed=True)

        self.assertIn("【实时行情】", report)
        self.assertIn("【近期量能】", report)
        self.assertIn("【换手率】", report)
        self.assertIn("【筹码分布】", report)
        self.assertIn("【资金流向】", report)
        self.assertIn("主力净流入", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
