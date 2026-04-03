#!/usr/bin/env python3
"""
板块分析测试。
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

from board_analyzer import (
    build_board_analysis_result,
    generate_board_report,
    match_board,
)


def sample_boards() -> list[dict]:
    return [
        {
            "code": "881121",
            "name": "半导体",
            "latest": 1234.56,
            "change_percent": 3.28,
            "change_amount": None,
            "market_cap": None,
            "up_count": 120,
            "down_count": 40,
            "board_type": "industry",
            "board_type_name": "行业板块",
        },
        {
            "code": "309121",
            "name": "AI PC",
            "latest": None,
            "change_percent": None,
            "change_amount": None,
            "market_cap": None,
            "up_count": None,
            "down_count": None,
            "board_type": "concept",
            "board_type_name": "概念板块",
        },
    ]


def sample_constituents() -> list[dict]:
    return [
        {
            "code": "688048",
            "name": "长光华芯",
            "price": 241.0,
            "change_percent": 11.29,
            "change_amount": 24.45,
            "volume_hands": None,
            "amount": 1992347303,
            "turnover_rate": 4.73,
            "volume_ratio": 3.74,
            "market_cap": 42483466263,
            "float_market_cap": 42483466263,
        },
        {
            "code": "688146",
            "name": "中船特气",
            "price": 46.58,
            "change_percent": 9.14,
            "change_amount": 3.90,
            "volume_hands": None,
            "amount": 406496083,
            "turnover_rate": 6.00,
            "volume_ratio": 10.80,
            "market_cap": 24660000014,
            "float_market_cap": 6752741820,
        },
        {
            "code": "600000",
            "name": "测试下跌股",
            "price": 10.02,
            "change_percent": -3.12,
            "change_amount": -0.32,
            "volume_hands": None,
            "amount": 102300000,
            "turnover_rate": 1.20,
            "volume_ratio": 0.88,
            "market_cap": 8800000000,
            "float_market_cap": 8600000000,
        },
    ]


class BoardAnalysisTests(unittest.TestCase):
    def test_match_board_prefers_exact_match(self) -> None:
        result = match_board("半导体", sample_boards())
        self.assertEqual(result["code"], "881121")

    @patch("board_analyzer.fetch_board_constituents")
    @patch("board_analyzer.fetch_board_list")
    def test_build_board_analysis_result_computes_summary_and_leaders(
        self,
        mock_fetch_board_list,
        mock_fetch_board_constituents,
    ) -> None:
        mock_fetch_board_list.return_value = sample_boards()
        mock_fetch_board_constituents.return_value = sample_constituents()

        result = build_board_analysis_result("半导体", top_n=2)

        self.assertEqual(result["board"]["code"], "881121")
        self.assertEqual(result["summary"]["constituent_count"], 3)
        self.assertEqual(result["summary"]["advancing_count"], 2)
        self.assertEqual(result["summary"]["declining_count"], 1)
        self.assertAlmostEqual(result["summary"]["average_change_percent"], 5.77, places=2)
        self.assertEqual(result["leaders"][0]["code"], "688048")
        self.assertEqual(len(result["top_losers"]), 2)

    @patch("board_analyzer.fetch_board_constituents")
    @patch("board_analyzer.fetch_board_list")
    def test_generate_board_report_contains_sections(
        self,
        mock_fetch_board_list,
        mock_fetch_board_constituents,
    ) -> None:
        mock_fetch_board_list.return_value = sample_boards()
        mock_fetch_board_constituents.return_value = sample_constituents()

        result = build_board_analysis_result("半导体", top_n=2)
        report = generate_board_report(result, top_n=2)

        self.assertIn("板块分析", report)
        self.assertIn("【龙头股】", report)
        self.assertIn("【涨幅居前】", report)
        self.assertIn("【跌幅居前】", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
