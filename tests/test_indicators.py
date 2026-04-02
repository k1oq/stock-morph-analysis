#!/usr/bin/env python3
"""
技术指标单元测试。
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from indicators import calc_bollinger, calc_macd, calc_rsi
from patterns import identify_engulfing_pattern


class IndicatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prices = [
            10.0, 10.2, 10.1, 10.4, 10.7, 10.6, 10.8, 11.0, 10.9, 11.2,
            11.4, 11.3, 11.6, 11.8, 11.7, 11.9, 12.1, 12.0, 12.2, 12.4,
            12.5, 12.7, 12.6, 12.9, 13.1, 13.0, 13.2, 13.4, 13.3, 13.5,
            13.7, 13.6, 13.8, 14.0, 14.2, 14.1, 14.4, 14.6, 14.5, 14.8,
        ]

    def test_calc_macd_returns_builtin_floats(self) -> None:
        result = calc_macd(self.prices)
        self.assertIsInstance(result["dif"], float)
        self.assertIsInstance(result["dea"], float)
        self.assertIsInstance(result["macd"], float)
        self.assertIn(result["signal"], {"金叉", "死叉", "多头上行", "空头下行"})

    def test_calc_rsi_stays_in_valid_range(self) -> None:
        result = calc_rsi(self.prices)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 100.0)

    def test_calc_bollinger_keeps_upper_middle_lower_order(self) -> None:
        result = calc_bollinger(self.prices)
        self.assertIsInstance(result["upper"], float)
        self.assertGreater(result["upper"], result["middle"])
        self.assertGreater(result["middle"], result["lower"])
        self.assertGreater(result["bandwidth"], 0.0)

    def test_identify_engulfing_pattern_detects_bullish_and_bearish(self) -> None:
        bullish = identify_engulfing_pattern(
            {"open": 9.0, "close": 10.5, "high": 10.6, "low": 8.9},
            {"open": 10.2, "close": 9.2, "high": 10.3, "low": 9.1},
        )
        bearish = identify_engulfing_pattern(
            {"open": 10.8, "close": 9.1, "high": 10.9, "low": 9.0},
            {"open": 9.4, "close": 10.4, "high": 10.5, "low": 9.3},
        )
        none_pattern = identify_engulfing_pattern(
            {"open": 10.02, "close": 10.08, "high": 10.12, "low": 9.99},
            {"open": 10.10, "close": 10.00, "high": 10.15, "low": 9.96},
        )

        self.assertEqual(bullish["type"], "看涨吞没")
        self.assertEqual(bearish["type"], "看跌吞没")
        self.assertEqual(none_pattern["type"], "无")


if __name__ == "__main__":
    unittest.main(verbosity=2)
