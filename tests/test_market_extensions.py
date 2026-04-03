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
    build_fund_flow_analysis,
    build_turnover_analysis,
    build_volume_profile,
)


def sample_realtime() -> dict:
    return {
        "price": 9.75,
        "change": 1.67,
        "amount_yi_yuan": 10.12,
        "turnover_rate": 4.69,
        "timestamp": "2026-04-03 15:00:00",
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

    def test_build_turnover_analysis_uses_tencent_realtime_turnover(self) -> None:
        result = build_turnover_analysis(sample_realtime())

        self.assertTrue(result["available"])
        self.assertEqual(result["latest_turnover_rate"], 4.69)
        self.assertEqual(result["activity_level"], "常态")
        self.assertEqual(result["source"], "tencent_realtime")

    def test_build_fund_flow_analysis_summarizes_recent_flow(self) -> None:
        result = build_fund_flow_analysis(sample_fund_flow_rows())

        self.assertTrue(result["available"])
        self.assertGreater(result["main_net_inflow_yi_yuan"], 0)
        self.assertGreater(result["cumulative_main_net_inflow_5d_yi_yuan"], 0)
        self.assertEqual(result["signal"], "偏多")


if __name__ == "__main__":
    unittest.main(verbosity=2)
