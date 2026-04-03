#!/usr/bin/env python3
"""
自选股批量分析测试。
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from morph_analyzer import (
    build_watchlist_analysis_result,
    export_watchlist_csv,
    generate_watchlist_report,
    load_watchlist_codes,
    sort_watchlist_summary,
)


def make_analysis_result(
    code: str,
    name: str,
    price: float,
    change_percent: float,
    score: float,
    action: str = "观望等待",
    warning_count: int = 0,
) -> dict:
    signal = "偏多" if score >= 0.5 else "偏空" if score <= -0.5 else "中性"
    return {
        "meta": {
            "code": code,
            "name": name,
            "generated_at": "2026-04-03T09:30:00",
        },
        "data_status": {
            "history": "complete",
            "indicators": "complete",
        },
        "warnings": ["warning"] * warning_count,
        "realtime": {
            "price": price,
            "change_percent": change_percent,
        },
        "score": {
            "total": score,
            "signal": signal,
        },
        "advice": {
            "action": action,
        },
    }


class WatchlistTests(unittest.TestCase):
    def test_load_watchlist_codes_skips_comments_blanks_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            watchlist = Path(temp_dir) / "stocks.txt"
            watchlist.write_text(
                "# 自选股\n600867\n\n600519 000001\n600867,300750\n",
                encoding="utf-8",
            )

            codes = load_watchlist_codes(str(watchlist))

        self.assertEqual(codes, ["600867", "600519", "000001", "300750"])

    @patch("morph_analyzer.build_analysis_result")
    def test_build_watchlist_analysis_result_sorts_and_collects_failures(self, mock_build) -> None:
        responses = {
            "000001": make_analysis_result("000001", "平安银行", 11.23, 1.36, 0.85, "持股观察"),
            "600519": make_analysis_result("600519", "贵州茅台", 1688.0, 0.92, 3.2, "持股待涨"),
        }

        def fake_build(code: str, days: int = 30) -> dict:
            if code == "600867":
                raise RuntimeError("network unavailable")
            return responses[code]

        mock_build.side_effect = fake_build

        result = build_watchlist_analysis_result(
            ["000001", "600519", "600867"],
            sort_by="score",
            descending=True,
            source="stocks.txt",
        )

        self.assertEqual([item["code"] for item in result["summary"]], ["600519", "000001"])
        self.assertEqual(result["summary"][0]["rank"], 1)
        self.assertEqual(result["meta"]["requested"], 3)
        self.assertEqual(result["meta"]["completed"], 2)
        self.assertEqual(result["meta"]["failed"], 1)
        self.assertEqual(result["failures"], [{"code": "600867", "error": "network unavailable"}])

    def test_sort_watchlist_summary_supports_change_sorting(self) -> None:
        entries = [
            {"code": "000001", "change_percent": 1.2, "score": 0.9},
            {"code": "600519", "change_percent": 3.4, "score": 1.1},
            {"code": "300750", "change_percent": -0.8, "score": 2.0},
        ]

        result = sort_watchlist_summary(entries, sort_by="change", descending=False)

        self.assertEqual([item["code"] for item in result], ["300750", "000001", "600519"])

    def test_export_watchlist_csv_writes_ranked_summary(self) -> None:
        batch_result = {
            "summary": [
                {
                    "rank": 1,
                    "code": "600519",
                    "name": "贵州茅台",
                    "price": 1688.0,
                    "change_percent": 0.92,
                    "score": 3.2,
                    "signal": "偏多",
                    "action": "持股待涨",
                    "warning_count": 0,
                    "history_status": "complete",
                    "indicator_status": "complete",
                    "generated_at": "2026-04-03T09:30:00",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "watchlist.csv"
            export_watchlist_csv(batch_result, str(output))

            with output.open("r", encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.reader(csv_file))

        self.assertEqual(rows[0][:4], ["排名", "代码", "名称", "最新价"])
        self.assertEqual(rows[1][0], "1")
        self.assertEqual(rows[1][1], "600519")
        self.assertEqual(rows[1][2], "贵州茅台")

    def test_generate_watchlist_report_contains_summary_and_failures(self) -> None:
        batch_result = {
            "meta": {
                "mode": "watchlist",
                "generated_at": "2026-04-03T09:30:00",
                "analysis_days": 30,
                "source": "stocks.txt",
                "requested": 3,
                "completed": 2,
                "failed": 1,
                "sort_by": "score",
                "sort_order": "desc",
            },
            "summary": [
                {
                    "rank": 1,
                    "code": "600519",
                    "name": "贵州茅台",
                    "price": 1688.0,
                    "change_percent": 0.92,
                    "score": 3.2,
                    "signal": "偏多",
                    "action": "持股待涨",
                }
            ],
            "results": [],
            "failures": [{"code": "600867", "error": "network unavailable"}],
        }

        report = generate_watchlist_report(batch_result)

        self.assertIn("自选股批量分析汇总", report)
        self.assertIn("排序方式：按评分降序", report)
        self.assertIn("600519", report)
        self.assertIn("【失败列表】", report)
        self.assertIn("600867: network unavailable", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
