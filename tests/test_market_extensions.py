#!/usr/bin/env python3
"""
扩展市场分析逻辑测试。
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from market_extensions import (
    build_chip_distribution_analysis,
    build_fund_flow_analysis,
    build_turnover_analysis,
    build_volume_profile,
)


def sample_realtime() -> dict:
    return {
        "price": 9.75,
        "change": 1.67,
        "amount_yi_yuan": 10.12,
    }


def sample_history_rows(count: int = 30) -> list[dict]:
    rows = []
    for day in range(1, count + 1):
        volume_shares = 70000000 + day * 500000
        if day == count:
            volume_shares *= 2.1
        rows.append(
            {
                "day": f"2026-03-{day:02d}",
                "open": 8.80 + day * 0.02,
                "high": 9.10 + day * 0.02,
                "low": 8.60 + day * 0.02,
                "close": 8.92 + day * 0.02,
                "volume_shares": volume_shares,
                "volume_hands": volume_shares / 100,
            }
        )
    return rows


def sample_market_history_rows(count: int = 60) -> list[dict]:
    rows = []
    for day in range(1, count + 1):
        volume_shares = 68000000 + day * 600000
        amount_yuan = 850000000 + day * 11000000
        turnover_rate = 2.2 + day * 0.04
        if day == count:
            turnover_rate = 8.9
        rows.append(
            {
                "date": f"2026-02-{day:02d}" if day <= 28 else f"2026-03-{day - 28:02d}",
                "open": 8.70 + day * 0.02,
                "close": 8.86 + day * 0.02,
                "high": 9.08 + day * 0.02,
                "low": 8.55 + day * 0.02,
                "volume_shares": volume_shares,
                "volume_hands": volume_shares / 100,
                "amount_yuan": amount_yuan,
                "amount_wan_yuan": amount_yuan / 10000,
                "amount_yi_yuan": amount_yuan / 100000000,
                "amplitude": 3.4,
                "change_percent": 1.1,
                "change_amount": 0.11,
                "turnover_rate": turnover_rate,
            }
        )
    return rows


def sample_fund_flow_rows(count: int = 5) -> list[dict]:
    rows = []
    for day in range(1, count + 1):
        main_net_inflow_yuan = 25000000 + day * 4000000
        rows.append(
            {
                "date": f"2026-03-{day:02d}",
                "main_net_inflow_yuan": main_net_inflow_yuan,
                "main_net_inflow_yi_yuan": main_net_inflow_yuan / 100000000,
                "small_net_inflow_yuan": -10000000.0,
                "medium_net_inflow_yuan": -4000000.0,
                "large_net_inflow_yuan": 13000000.0,
                "super_large_net_inflow_yuan": 18000000.0,
                "main_net_inflow_ratio": 5.8,
                "small_net_inflow_ratio": -2.0,
                "medium_net_inflow_ratio": -1.1,
                "large_net_inflow_ratio": 1.8,
                "super_large_net_inflow_ratio": 3.1,
                "close": 9.75,
                "change_percent": 1.2,
            }
        )
    return rows


class MarketExtensionsTests(unittest.TestCase):
    def test_build_volume_profile_reports_recent_volume_state(self) -> None:
        result = build_volume_profile(sample_realtime(), sample_history_rows())

        self.assertTrue(result["available"])
        self.assertIsNotNone(result["volume_ratio_5"])
        self.assertEqual(result["signal"], "偏多")

    def test_build_turnover_analysis_reports_activity_level(self) -> None:
        result = build_turnover_analysis(sample_realtime(), sample_market_history_rows())

        self.assertTrue(result["available"])
        self.assertIn(result["activity_level"], {"活跃", "高换手"})
        self.assertEqual(result["signal"], "偏多")

    def test_build_chip_distribution_analysis_returns_cost_ranges(self) -> None:
        result = build_chip_distribution_analysis(9.75, sample_market_history_rows())

        self.assertTrue(result["available"])
        self.assertLessEqual(result["cost_range_90"]["low"], result["cost_range_90"]["high"])
        self.assertIsNotNone(result["average_cost"])
        self.assertIn(result["signal"], {"偏多", "中性", "偏空"})

    def test_build_fund_flow_analysis_summarizes_recent_flow(self) -> None:
        result = build_fund_flow_analysis(sample_fund_flow_rows())

        self.assertTrue(result["available"])
        self.assertGreater(result["main_net_inflow_yi_yuan"], 0)
        self.assertGreater(result["cumulative_main_net_inflow_5d_yi_yuan"], 0)
        self.assertEqual(result["signal"], "偏多")


if __name__ == "__main__":
    unittest.main(verbosity=2)
