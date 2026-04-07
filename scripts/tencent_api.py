#!/usr/bin/env python3
"""
腾讯财经实时行情接口。
数据源：http://qt.gtimg.cn/
"""
from __future__ import annotations

from datetime import datetime
import time
from typing import Dict, List, Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://stockapp.finance.qq.com/",
}


def get_market_symbol(code: str) -> str:
    """
    将股票代码转换成腾讯财经需要的市场前缀。
    """
    normalized = str(code).strip()
    if normalized.startswith("6"):
        return f"sh{normalized}"
    if normalized.startswith(("0", "3")):
        return f"sz{normalized}"
    if normalized.startswith(("8", "4", "9")):
        return f"sh{normalized}"
    raise ValueError(f"未知的股票代码前缀：{code}")


def _safe_float(value: str, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_timestamp(raw_value: str) -> str:
    if not raw_value:
        return ""
    try:
        return datetime.strptime(raw_value, "%Y%m%d%H%M%S").isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return raw_value


def _request_text(
    url: str,
    retries: int = 3,
    raise_on_error: bool = False,
) -> Optional[str]:
    last_error = "未知错误"

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS)
            response.raise_for_status()
            response.encoding = "gbk"
            payload = response.text.strip()
            if not payload:
                raise RuntimeError("腾讯接口返回空响应")
            return payload
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))

    if raise_on_error:
        raise RuntimeError(last_error)
    return None


def get_realtime_data(
    code: str,
    retries: int = 3,
    raise_on_error: bool = False,
) -> Optional[Dict]:
    """
    获取个股实时行情数据。

    返回字段中：
    - volume / volume_hands: 手
    - volume_shares: 股
    - amount / amount_wan_yuan: 万元
    - amount_yi_yuan: 亿元
    """
    try:
        symbol = get_market_symbol(code)
    except ValueError as exc:
        if raise_on_error:
            raise RuntimeError(str(exc)) from exc
        return None

    url = f"http://qt.gtimg.cn/q={symbol}"
    payload = _request_text(url, retries=retries, raise_on_error=raise_on_error)
    if payload is None:
        return None

    if "=" not in payload:
        message = "腾讯接口返回格式异常"
        if raise_on_error:
            raise RuntimeError(message)
        return None

    try:
        content = payload.split("=", 1)[1].strip().rstrip(";").strip('"')
        fields = content.split("~")
        if len(fields) < 58:
            raise ValueError(f"数据字段不足：{len(fields)}")

        price = _safe_float(fields[3])
        prev_close = _safe_float(fields[4])
        open_price = _safe_float(fields[5])
        volume_hands = _safe_float(fields[6])
        amount_wan_yuan = _safe_float(fields[57] or fields[37])
        high_price = _safe_float(fields[33])
        low_price = _safe_float(fields[34])
        turnover_rate = _safe_float(fields[38]) if len(fields) > 38 else None

        change_amount = price - prev_close if prev_close else 0.0
        change_percent = (change_amount / prev_close * 100) if prev_close else 0.0

        result = {
            "code": str(code).strip(),
            "symbol": symbol,
            "name": fields[1],
            "price": price,
            "prev_close": prev_close,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "change_amount": change_amount,
            "change": change_percent,
            "volume": volume_hands,
            "volume_hands": volume_hands,
            "volume_shares": volume_hands * 100,
            "amount": amount_wan_yuan,
            "amount_wan_yuan": amount_wan_yuan,
            "amount_yi_yuan": amount_wan_yuan / 10000 if amount_wan_yuan else 0.0,
            "turnover_rate": turnover_rate,
            "timestamp": _format_timestamp(fields[30]),
        }
        return result
    except (IndexError, ValueError) as exc:
        if raise_on_error:
            raise RuntimeError(f"实时行情解析失败：{exc}") from exc
        return None


def get_multiple_realtime_data(
    codes: List[str],
    retries: int = 3,
) -> List[Dict]:
    """
    批量获取多只股票的实时数据。
    """
    results: List[Dict] = []
    for code in codes:
        data = get_realtime_data(code, retries=retries)
        if data:
            results.append(data)
    return results


if __name__ == "__main__":
    import json

    sample = get_realtime_data("600867", raise_on_error=True)
    print(json.dumps(sample, indent=2, ensure_ascii=False))
