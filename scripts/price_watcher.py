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
from pathlib import Path
import requests
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
VALID_OPENCLAW_ENDPOINTS = {"agent", "wake"}


@dataclass(frozen=True)
class WatcherRule:
    id: str
    code: str
    target_price: float
    direction: str
    enabled: bool = True
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS


@dataclass(frozen=True)
class OpenClawHookConfig:
    base_url: str
    token: str
    endpoint: str = "agent"
    wake_mode: str = "next-heartbeat"
    name: str = "Stock Watcher"
    deliver: Optional[bool] = None
    channel: Optional[str] = None
    to: Optional[str] = None
    model: Optional[str] = None
    thinking: Optional[str] = None
    timeout_seconds: int = 10


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


def parse_openclaw_config(raw_config: Any) -> OpenClawHookConfig:
    if not isinstance(raw_config, dict):
        raise ValueError("openclaw 必须是对象")

    base_url = _require_string(raw_config.get("base_url"), "openclaw.base_url").rstrip("/")
    token = _require_string(raw_config.get("token"), "openclaw.token")
    endpoint = _require_string(raw_config.get("endpoint", "agent"), "openclaw.endpoint").lower()
    if endpoint not in VALID_OPENCLAW_ENDPOINTS:
        raise ValueError("openclaw.endpoint 必须是 agent 或 wake")

    wake_mode = _require_string(raw_config.get("wake_mode", "next-heartbeat"), "openclaw.wake_mode")
    if wake_mode not in {"now", "next-heartbeat"}:
        raise ValueError("openclaw.wake_mode 必须是 now 或 next-heartbeat")

    timeout_seconds = _require_int(raw_config.get("timeout_seconds", 10), "openclaw.timeout_seconds")
    if timeout_seconds <= 0:
        raise ValueError("openclaw.timeout_seconds 必须大于 0")

    deliver = raw_config.get("deliver")
    if deliver is not None and not isinstance(deliver, bool):
        raise ValueError("openclaw.deliver 必须是布尔值")

    optional_fields = {}
    for field_name in ("channel", "to", "model", "thinking", "name"):
        value = raw_config.get(field_name)
        if value is None:
            continue
        optional_fields[field_name] = _require_string(value, f"openclaw.{field_name}")

    return OpenClawHookConfig(
        base_url=base_url,
        token=token,
        endpoint=endpoint,
        wake_mode=wake_mode,
        name=optional_fields.get("name", "Stock Watcher"),
        deliver=deliver,
        channel=optional_fields.get("channel"),
        to=optional_fields.get("to"),
        model=optional_fields.get("model"),
        thinking=optional_fields.get("thinking"),
        timeout_seconds=timeout_seconds,
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
        "openclaw": parse_openclaw_config(raw_config.get("openclaw")),
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


def format_event_message(event: Dict[str, Any]) -> str:
    direction_text = "达到或高于" if event["direction"] == "gte" else "达到或低于"
    lines = [
        "股票价格提醒",
        f"规则ID: {event['rule_id']}",
        f"股票: {event['name']} ({event['code']})",
        f"当前价格: {event['current_price']:.2f}",
        f"目标价格: {event['target_price']:.2f}",
        f"触发条件: {direction_text}",
    ]
    if event["timestamp"]:
        lines.append(f"行情时间: {event['timestamp']}")
    lines.append(f"触发时间: {event['triggered_at']}")
    return "\n".join(lines)


def write_event_file(event_dir: Path, event: Dict[str, Any]) -> Path:
    ensure_directory(event_dir)
    file_name = f"{event['triggered_at'].replace(':', '-').replace('T', '_')}_{event['rule_id']}_{event['event_id']}.json"
    event_path = event_dir / file_name
    event_path.write_text(json.dumps(event, indent=2, ensure_ascii=False), encoding="utf-8")
    return event_path


def build_openclaw_payload(event: Dict[str, Any], hook_config: OpenClawHookConfig, event_path: Path) -> Dict[str, Any]:
    message = format_event_message(event)
    if hook_config.endpoint == "wake":
        return {
            "text": f"{message}\nevent_file={event_path}",
            "mode": hook_config.wake_mode,
        }

    payload: Dict[str, Any] = {
        "message": f"{message}\nevent_file={event_path}",
        "name": hook_config.name,
        "wakeMode": hook_config.wake_mode,
    }
    if hook_config.deliver is not None:
        payload["deliver"] = hook_config.deliver
    if hook_config.channel:
        payload["channel"] = hook_config.channel
    if hook_config.to:
        payload["to"] = hook_config.to
    if hook_config.model:
        payload["model"] = hook_config.model
    if hook_config.thinking:
        payload["thinking"] = hook_config.thinking
    return payload


def send_openclaw_webhook(hook_config: OpenClawHookConfig, event: Dict[str, Any], event_path: Path) -> None:
    endpoint_path = "agent" if hook_config.endpoint == "agent" else "wake"
    url = f"{hook_config.base_url}/hooks/{endpoint_path}"
    headers = {
        "Content-Type": "application/json",
        "x-openclaw-token": hook_config.token,
    }
    payload = build_openclaw_payload(event, hook_config, event_path)

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=hook_config.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"openclaw webhook 请求失败: {exc}") from exc

    if response.status_code >= 400:
        body = response.text.strip()
        raise RuntimeError(f"openclaw webhook 调用失败: HTTP {response.status_code} {body}")


def dispatch_openclaw_event(hook_config: OpenClawHookConfig, event: Dict[str, Any], event_path: Path) -> None:
    send_openclaw_webhook(hook_config, event, event_path)


def update_rule_state(
    state: Dict[str, Any],
    rule: WatcherRule,
    quote: Dict[str, Any],
    now: datetime,
    triggered: bool,
    event_path: Optional[Path] = None,
    delivery_status: Optional[str] = None,
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
    if event_path is not None:
        current["last_event_file"] = str(event_path)
    if delivery_status is not None:
        current["last_delivery_status"] = delivery_status
    rules_state[rule.id] = current


def check_rule(
    rule: WatcherRule,
    quote: Dict[str, Any],
    state: Dict[str, Any],
    hook_config: OpenClawHookConfig,
    event_dir: Path,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    rule_state = state.get("rules", {}).get(rule.id, {})
    matched = rule_matches(rule, float(quote["price"]))
    if not matched:
        update_rule_state(state, rule, quote, now, triggered=False, delivery_status="not_matched")
        return None

    if is_in_cooldown(rule, rule_state, now):
        update_rule_state(state, rule, quote, now, triggered=False, delivery_status="cooldown")
        return None

    event = build_event(rule, quote, now)
    event_path = write_event_file(event_dir, event)
    try:
        dispatch_openclaw_event(hook_config, event, event_path)
    except RuntimeError:
        update_rule_state(
            state,
            rule,
            quote,
            now,
            triggered=False,
            event_path=event_path,
            delivery_status="webhook_failed",
        )
        raise

    update_rule_state(
        state,
        rule,
        quote,
        now,
        triggered=True,
        event_path=event_path,
        delivery_status="delivered",
    )
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
                hook_config=config["openclaw"],
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
