#!/usr/bin/env python3
"""
盘后复盘测试。
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from daily_review import (
    build_daily_review_result,
    build_hot_boards,
    generate_daily_review_report,
    normalize_trade_date,
)


def sample_limit_up_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "600488",
                "名称": "津药药业",
                "涨跌幅": 9.94,
                "最新价": 6.97,
                "成交额": 583902992,
                "封板资金": 339756009,
                "连板数": 6,
                "所属行业": "化学制药",
            },
            {
                "代码": "000950",
                "名称": "重药控股",
                "涨跌幅": 10.01,
                "最新价": 7.14,
                "成交额": 1003031312,
                "封板资金": 232752576,
                "连板数": 2,
                "所属行业": "化学制药",
            },
            {
                "代码": "603123",
                "名称": "翠微股份",
                "涨跌幅": 10.03,
                "最新价": 11.96,
                "成交额": 649021840,
                "封板资金": 508739506,
                "连板数": 1,
                "所属行业": "多元金融",
            },
        ]
    )


def sample_limit_down_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "002800",
                "名称": "天顺股份",
                "涨跌幅": -10.0,
                "连续跌停": 1,
                "所属行业": "物流",
            }
        ]
    )


def sample_strong_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "300006",
                "名称": "莱美药业",
                "涨跌幅": 16.02,
                "成交额": 691612336,
                "所属行业": "化学制药",
            },
            {
                "代码": "688205",
                "名称": "德科立",
                "涨跌幅": 19.30,
                "成交额": 2039075664,
                "所属行业": "通信设备",
            },
        ]
    )


class DailyReviewTests(unittest.TestCase):
    def test_normalize_trade_date_accepts_hyphenated_format(self) -> None:
        self.assertEqual(normalize_trade_date("2026-04-03"), "20260403")

    def test_build_hot_boards_prefers_limit_up_clusters(self) -> None:
        hot_boards = build_hot_boards(sample_limit_up_df(), sample_strong_df(), top_n=3)

        self.assertEqual(hot_boards[0]["board"], "化学制药")
        self.assertEqual(hot_boards[0]["limit_up_count"], 2)
        self.assertEqual(hot_boards[0]["highest_lianban"], 6)
        self.assertIn("津药药业", hot_boards[0]["leader_stock"])

    @patch("daily_review.fetch_review_data")
    def test_build_daily_review_result_identifies_consecutive_limit_up(self, mock_fetch) -> None:
        mock_fetch.return_value = {
            "limit_up": sample_limit_up_df(),
            "limit_down": sample_limit_down_df(),
            "strong": sample_strong_df(),
        }

        result = build_daily_review_result("2026-04-03")

        self.assertEqual(result["summary"]["limit_up_count"], 3)
        self.assertEqual(result["summary"]["limit_down_count"], 1)
        self.assertEqual(result["summary"]["consecutive_limit_up_count"], 2)
        self.assertEqual(result["summary"]["highest_limit_up_streak"], 6)
        self.assertEqual(result["hot_boards"][0]["board"], "化学制药")

    @patch("daily_review.fetch_review_data")
    def test_generate_daily_review_report_contains_key_sections(self, mock_fetch) -> None:
        mock_fetch.return_value = {
            "limit_up": sample_limit_up_df(),
            "limit_down": sample_limit_down_df(),
            "strong": sample_strong_df(),
        }

        result = build_daily_review_result("2026-04-03")
        report = generate_daily_review_report(result, top_n=5)

        self.assertIn("盘后复盘", report)
        self.assertIn("【涨停概览】", report)
        self.assertIn("【连板股】", report)
        self.assertIn("【热点板块】", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
