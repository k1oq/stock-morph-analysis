#!/usr/bin/env python3
"""
联网 smoke test：验证腾讯实时接口和新浪历史 K 线接口。
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sina_history import get_history_kline
from tencent_api import get_realtime_data


class LiveApiTests(unittest.TestCase):
    STOCK_CODES = ("600867", "600519", "000001")

    def test_realtime_api_returns_core_fields(self) -> None:
        for code in self.STOCK_CODES:
            with self.subTest(code=code):
                data = get_realtime_data(code, raise_on_error=True)
                self.assertEqual(data["code"], code)
                self.assertTrue(data["name"])
                self.assertGreater(data["price"], 0)
                self.assertGreaterEqual(data["high"], data["low"])
                self.assertGreater(data["volume_hands"], 0)
                self.assertGreater(data["amount_wan_yuan"], 0)

    def test_history_api_returns_daily_bars(self) -> None:
        for code in self.STOCK_CODES:
            with self.subTest(code=code):
                rows = get_history_kline(code, datalen=30, raise_on_error=True)
                self.assertGreaterEqual(len(rows), 30)
                self.assertLess(rows[0]["day"], rows[-1]["day"])
                self.assertGreater(rows[-1]["close"], 0)
                self.assertGreater(rows[-1]["volume_shares"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
