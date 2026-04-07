#!/usr/bin/env python3
"""
股价阈值监控脚本。

使用方式:
    python scripts/price_watcher.py --config watcher.json --once
    python scripts/price_watcher.py --config watcher.json --interval 30
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from tencent_api import get_realtime_data


DEFAULT_EVENT_DIR = Path("runtime/events")
DEFAULT_STATE_FILE = Path("runtime/price_watcher_state.json")
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_COOLDOWN_SECONDS = 300
VALID_DIRECTIONS = {"gte", "lte"}


@dataclass(frozen=True)
class WatcherRule:
    id: str
    code: str
    target_price: float
    direction: str
    enabled: bool = True
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS


def parse_command(command_value: Any) -> List[str]:
    if command_value is None:
        return ["openclaw"]

    if isinstance(command_value, str):
        parsed = shlex.split(command_value, posix=os.name != "nt")
        if not parsed:
            raise ValueError("openclaw_command 不能为空字符串")
        return parsed

    if isinstance(command_value, list) and all(isinstance(item, str) and item.strip() for item in command_value):
        return list(command_value)

    raise ValueError("openclaw_command 必须是字符串或字符串数组")


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _require_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是数字") from exc


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是整数")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc


def parse_watcher_rule(raw_rule: Dict[str, Any], index: int) -> WatcherRule:
    if not isinstance(raw_rule, dict):
        raise ValueError(f"watchers[{index}] 必须是对象")

    rule_id = _require_string(raw_rule.get("id"), f"watchers[{index}].id")
    code = _require_string(raw_rule.get("code"), f"watchers[{index}].code")
    target_price = _require_float(raw_rule.get("target_price"), f"watchers[{index}].target_price")
    if target_price <= 0:
        raise ValueError(f"watchers[{index}].target_price 必须大于 0")

    direction = _require_string(raw_rule.get("direction"), f"watchers[{index}].direction").lower()
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"watchers[{index}].direction 必须是 gte 或 lte")

    enabled = raw_rule.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"watchers[{index}].enabled 必须是布尔值")

    cooldown_seconds = _require_int(
        raw_rule.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS),
        f"watchers[{index}].cooldown_seconds",
    )
    if cooldown_seconds < 0:
        raise ValueError(f"watchers[{index}].cooldown_seconds 不能小于 0")

    return WatcherRule(
        id=rule_id,
        code=code,
        target_price=target_price,
        direction=direction,
        enabled=enabled,
        cooldown_seconds=cooldown_seconds,
    )


def load_config(path: str) -> Dict[str, Any]:
    config_path = Path(path)
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"读取配置文件失败: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是合法 JSON: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ValueError("配置文件顶层必须是对象")

    raw_watchers = raw_config.get("watchers")
    if not isinstance(raw_watchers, list) or not raw_watchers:
        raise ValueError("watchers 必须是非空数组")

    watchers = [parse_watcher_rule(item, index) for index, item in enumerate(raw_watchers)]
    watcher_ids = [item.id for item in watchers]
    if len(watcher_ids) != len(set(watcher_ids)):
        raise ValueError("watchers.id 不能重复")

    event_dir = Path(raw_config.get("event_dir", DEFAULT_EVENT_DIR))
    state_file = Path(raw_config.get("state_file", DEFAULT_STATE_FILE))
    if event_dir.exists() and not event_dir.is_dir():
        raise ValueError("event_dir 必须是目录路径")

    return {
        "config_path": str(config_path),
        "openclaw_command": parse_command(raw_config.get("openclaw_command")),
        "event_dir": event_dir,
        "state_file": state_file,
        "watchers": watchers,
    }


def load_state(path: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    if not path.exists():
        return {"rules": {}}, None

    try:
        raw_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"rules": {}}, f"状态文件损坏，已重置: {path}"

    if not isinstance(raw_state, dict):
        return {"rules": {}}, f"状态文件格式异常，已重置: {path}"

    raw_rules = raw_state.get("rules", {})
    if not isinstance(raw_rules, dict):
        return {"rules": {}}, f"状态文件格式异常，已重置: {path}"

    return {"rules": raw_rules}, None


def save_state(path: Path, state: Dict[str, Any]) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def rule_matches(rule: WatcherRule, current_price: float) -> bool:
    if rule.direction == "gte":
        return current_price >= rule.target_price
    return current_price <= rule.target_price


def is_in_cooldown(rule: WatcherRule, rule_state: Dict[str, Any], now: datetime) -> bool:
    last_triggered_at = parse_iso_datetime(rule_state.get("last_triggered_at"))
    if last_triggered_at is None:
        return False
    return now < last_triggered_at + timedelta(seconds=rule.cooldown_seconds)


def build_event(rule: WatcherRule, quote: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "triggered_at": now.isoformat(timespec="seconds"),
        "rule_id": rule.id,
        "code": quote["code"],
        "name": quote["name"],
        "current_price": round(float(quote["price"]), 2),
        "target_price": round(rule.target_price, 2),
        "direction": rule.direction,
        "timestamp": quote.get("timestamp") or "",
    }


def write_event_file(event_dir: Path, event: Dict[str, Any]) -> Path:
    ensure_directory(event_dir)
    file_name = f"{event['triggered_at'].replace(':', '-').replace('T', '_')}_{event['rule_id']}_{event['event_id']}.json"
    event_path = event_dir / file_name
    event_path.write_text(json.dumps(event, indent=2, ensure_ascii=False), encoding="utf-8")
    return event_path


def invoke_openclaw(command: List[str], event_path: Path) -> None:
    result = subprocess.run(
        [*command, str(event_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(message)


def update_rule_state(
    state: Dict[str, Any],
    rule: WatcherRule,
    quote: Dict[str, Any],
    now: datetime,
    triggered: bool,
) -> None:
    rules_state = state.setdefault("rules", {})
    current = rules_state.get(rule.id, {})
    current["last_price"] = round(float(quote["price"]), 2)
    current["last_checked_at"] = now.isoformat(timespec="seconds")
    current["last_quote_timestamp"] = quote.get("timestamp") or ""
    if triggered:
        current["last_triggered_at"] = now.isoformat(timespec="seconds")
        current["last_target_price"] = round(rule.target_price, 2)
        current["last_direction"] = rule.direction
    rules_state[rule.id] = current


def check_rule(
    rule: WatcherRule,
    quote: Dict[str, Any],
    state: Dict[str, Any],
    command: List[str],
    event_dir: Path,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    rule_state = state.get("rules", {}).get(rule.id, {})
    matched = rule_matches(rule, float(quote["price"]))
    if not matched:
        update_rule_state(state, rule, quote, now, triggered=False)
        return None

    if is_in_cooldown(rule, rule_state, now):
        update_rule_state(state, rule, quote, now, triggered=False)
        return None

    event = build_event(rule, quote, now)
    event_path = write_event_file(event_dir, event)
    try:
        invoke_openclaw(command, event_path)
    except RuntimeError:
        update_rule_state(state, rule, quote, now, triggered=False)
        raise

    update_rule_state(state, rule, quote, now, triggered=True)
    return event


def run_watch_cycle(config: Dict[str, Any], state: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    cycle_time = now or datetime.now()
    results = {
        "checked": 0,
        "triggered": [],
        "errors": [],
        "warnings": [],
    }

    for rule in config["watchers"]:
        if not rule.enabled:
            continue

        results["checked"] += 1
        try:
            quote = get_realtime_data(rule.code, raise_on_error=True)
            event = check_rule(
                rule=rule,
                quote=quote,
                state=state,
                command=config["openclaw_command"],
                event_dir=config["event_dir"],
                now=cycle_time,
            )
            if event:
                results["triggered"].append(event)
        except RuntimeError as exc:
            results["errors"].append({"rule_id": rule.id, "code": rule.code, "error": str(exc)})

    return results


def format_cycle_summary(cycle_result: Dict[str, Any]) -> str:
    return (
        f"checked={cycle_result['checked']} "
        f"triggered={len(cycle_result['triggered'])} "
        f"errors={len(cycle_result['errors'])}"
    )


def monitor(config: Dict[str, Any], once: bool = False, interval: int = DEFAULT_INTERVAL_SECONDS) -> int:
    state, warning = load_state(config["state_file"])
    if warning:
        print(warning, file=sys.stderr)

    while True:
        cycle_result = run_watch_cycle(config, state)
        save_state(config["state_file"], state)

        for event in cycle_result["triggered"]:
            print(
                f"triggered rule={event['rule_id']} code={event['code']} "
                f"price={event['current_price']:.2f} target={event['target_price']:.2f}"
            )
        for error in cycle_result["errors"]:
            print(
                f"error rule={error['rule_id']} code={error['code']} message={error['error']}",
                file=sys.stderr,
            )

        if once:
            return 1 if cycle_result["errors"] else 0

        print(format_cycle_summary(cycle_result))
        time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="股价阈值监控工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/price_watcher.py --config watcher.json --once
  python scripts/price_watcher.py --config watcher.json --interval 30
        """,
    )
    parser.add_argument("--config", required=True, help="监控配置 JSON 路径")
    parser.add_argument("--once", action="store_true", help="执行一轮检查后退出")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="常驻模式轮询间隔秒数，默认 30",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.interval <= 0:
        print("--interval 必须大于 0", file=sys.stderr)
        raise SystemExit(1)

    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    exit_code = monitor(config, once=args.once, interval=args.interval)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
