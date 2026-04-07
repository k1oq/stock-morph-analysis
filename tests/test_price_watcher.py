#!/usr/bin/env python3
"""
股价监控流程测试。
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from price_watcher import (
    DEFAULT_COOLDOWN_SECONDS,
    OpenClawHookConfig,
    WatcherRule,
    build_openclaw_payload,
    check_rule,
    load_config,
    load_state,
    run_watch_cycle,
    save_state,
)


def sample_quote(code: str = "600519", price: float = 1688.0) -> dict:
    return {
        "code": code,
        "name": "贵州茅台",
        "price": price,
        "timestamp": "2026-04-07 10:30:00",
    }


class PriceWatcherTests(unittest.TestCase):
    def test_load_config_applies_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "watcher.json"
            config_path.write_text(
                json.dumps(
                    {
                        "openclaw": {
                            "base_url": "http://127.0.0.1:18789",
                            "token": "secret-token"
                        },
                        "watchers": [
                            {
                                "id": "moutai-gte",
                                "code": "600519",
                                "target_price": 1680,
                                "direction": "gte",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_config(str(config_path))

        self.assertEqual(config["openclaw"].base_url, "http://127.0.0.1:18789")
        self.assertEqual(config["openclaw"].endpoint, "agent")
        self.assertEqual(config["watchers"][0].cooldown_seconds, DEFAULT_COOLDOWN_SECONDS)

    def test_build_openclaw_payload_uses_agent_endpoint_shape(self) -> None:
        hook_config = OpenClawHookConfig(
            base_url="http://127.0.0.1:18789",
            token="secret-token",
            endpoint="agent",
            wake_mode="next-heartbeat",
        )
        event = {
            "rule_id": "moutai-gte",
            "name": "贵州茅台",
            "code": "600519",
            "current_price": 1688.0,
            "target_price": 1680.0,
            "direction": "gte",
            "timestamp": "2026-04-07 10:30:00",
            "triggered_at": "2026-04-07T10:35:00",
        }

        payload = build_openclaw_payload(event, hook_config, Path("runtime/events/event.json"))

        self.assertEqual(payload["name"], "Stock Watcher")
        self.assertEqual(payload["wakeMode"], "next-heartbeat")
        self.assertIn("message", payload)
        self.assertIn("event_file=runtime", payload["message"])

    def test_check_rule_triggers_gte_and_writes_event(self) -> None:
        rule = WatcherRule(id="moutai-gte", code="600519", target_price=1680.0, direction="gte")
        state = {"rules": {}}
        now = datetime(2026, 4, 7, 10, 35, 0)
        hook_config = OpenClawHookConfig(base_url="http://127.0.0.1:18789", token="secret-token")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("price_watcher.dispatch_openclaw_event") as mock_dispatch:
                event = check_rule(
                    rule=rule,
                    quote=sample_quote(price=1688.0),
                    state=state,
                    hook_config=hook_config,
                    event_dir=Path(temp_dir),
                    now=now,
                )

            self.assertIsNotNone(event)
            self.assertEqual(event["rule_id"], "moutai-gte")
            self.assertEqual(event["direction"], "gte")
            files = list(Path(temp_dir).glob("*.json"))
            payload = json.loads(files[0].read_text(encoding="utf-8"))

        mock_dispatch.assert_called_once()
        self.assertEqual(len(files), 1)
        self.assertEqual(payload["current_price"], 1688.0)
        self.assertEqual(state["rules"]["moutai-gte"]["last_triggered_at"], now.isoformat(timespec="seconds"))
        self.assertEqual(state["rules"]["moutai-gte"]["last_delivery_status"], "delivered")

    def test_check_rule_triggers_lte(self) -> None:
        rule = WatcherRule(id="pingan-lte", code="000001", target_price=10.5, direction="lte")
        state = {"rules": {}}
        hook_config = OpenClawHookConfig(base_url="http://127.0.0.1:18789", token="secret-token")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("price_watcher.dispatch_openclaw_event"):
                event = check_rule(
                    rule=rule,
                    quote=sample_quote(code="000001", price=10.2),
                    state=state,
                    hook_config=hook_config,
                    event_dir=Path(temp_dir),
                    now=datetime(2026, 4, 7, 10, 36, 0),
                )

        self.assertIsNotNone(event)
        self.assertEqual(event["direction"], "lte")

    def test_check_rule_does_not_trigger_when_price_not_met(self) -> None:
        rule = WatcherRule(id="moutai-gte", code="600519", target_price=1700.0, direction="gte")
        state = {"rules": {}}
        hook_config = OpenClawHookConfig(base_url="http://127.0.0.1:18789", token="secret-token")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("price_watcher.dispatch_openclaw_event") as mock_dispatch:
                event = check_rule(
                    rule=rule,
                    quote=sample_quote(price=1688.0),
                    state=state,
                    hook_config=hook_config,
                    event_dir=Path(temp_dir),
                    now=datetime(2026, 4, 7, 10, 37, 0),
                )

        self.assertIsNone(event)
        mock_dispatch.assert_not_called()
        self.assertEqual(state["rules"]["moutai-gte"]["last_delivery_status"], "not_matched")

    def test_check_rule_respects_cooldown(self) -> None:
        rule = WatcherRule(id="moutai-gte", code="600519", target_price=1680.0, direction="gte", cooldown_seconds=300)
        now = datetime(2026, 4, 7, 10, 40, 0)
        hook_config = OpenClawHookConfig(base_url="http://127.0.0.1:18789", token="secret-token")
        state = {
            "rules": {
                "moutai-gte": {
                    "last_triggered_at": (now - timedelta(seconds=120)).isoformat(timespec="seconds")
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("price_watcher.dispatch_openclaw_event") as mock_dispatch:
                event = check_rule(
                    rule=rule,
                    quote=sample_quote(price=1688.0),
                    state=state,
                    hook_config=hook_config,
                    event_dir=Path(temp_dir),
                    now=now,
                )

        self.assertIsNone(event)
        mock_dispatch.assert_not_called()
        self.assertEqual(state["rules"]["moutai-gte"]["last_delivery_status"], "cooldown")

    def test_check_rule_allows_retrigger_after_cooldown(self) -> None:
        rule = WatcherRule(id="moutai-gte", code="600519", target_price=1680.0, direction="gte", cooldown_seconds=300)
        now = datetime(2026, 4, 7, 10, 45, 0)
        hook_config = OpenClawHookConfig(base_url="http://127.0.0.1:18789", token="secret-token")
        state = {
            "rules": {
                "moutai-gte": {
                    "last_triggered_at": (now - timedelta(seconds=301)).isoformat(timespec="seconds")
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("price_watcher.dispatch_openclaw_event") as mock_dispatch:
                event = check_rule(
                    rule=rule,
                    quote=sample_quote(price=1688.0),
                    state=state,
                    hook_config=hook_config,
                    event_dir=Path(temp_dir),
                    now=now,
                )

        self.assertIsNotNone(event)
        mock_dispatch.assert_called_once()

    @patch("price_watcher.get_realtime_data")
    @patch("price_watcher.dispatch_openclaw_event")
    def test_run_watch_cycle_collects_partial_errors(self, mock_dispatch, mock_quote) -> None:
        mock_quote.side_effect = [
            sample_quote(code="600519", price=1688.0),
            RuntimeError("network unavailable"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "openclaw": OpenClawHookConfig(base_url="http://127.0.0.1:18789", token="secret-token"),
                "event_dir": Path(temp_dir),
                "watchers": [
                    WatcherRule(id="moutai-gte", code="600519", target_price=1680.0, direction="gte"),
                    WatcherRule(id="pingan-lte", code="000001", target_price=10.5, direction="lte"),
                ],
            }
            state = {"rules": {}}

            result = run_watch_cycle(config, state, now=datetime(2026, 4, 7, 10, 50, 0))

        self.assertEqual(result["checked"], 2)
        self.assertEqual(len(result["triggered"]), 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "000001")
        mock_dispatch.assert_called_once()

    def test_load_state_resets_when_file_is_corrupted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text("{bad json", encoding="utf-8")

            state, warning = load_state(state_path)

        self.assertEqual(state, {"rules": {}})
        self.assertIn("状态文件损坏", warning)

    def test_save_and_load_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state = {
                "rules": {
                    "moutai-gte": {
                        "last_price": 1688.0,
                        "last_checked_at": "2026-04-07T10:55:00",
                        "last_triggered_at": "2026-04-07T10:50:00",
                    }
                }
            }

            save_state(state_path, state)
            loaded_state, warning = load_state(state_path)

        self.assertIsNone(warning)
        self.assertEqual(loaded_state, state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
