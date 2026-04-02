#!/usr/bin/env python3
"""
新浪财经历史 K 线接口。
数据源：http://money.finance.sina.com.cn/
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests

from tencent_api import get_market_symbol


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://finance.sina.com.cn/",
}


def _safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_history_row(raw_row: Dict) -> Optional[Dict]:
    day = str(raw_row.get("day", "")).strip()
    if not day:
        return None

    volume_shares = _safe_float(raw_row.get("volume"))
    return {
        "day": day,
        "open": _safe_float(raw_row.get("open")),
        "high": _safe_float(raw_row.get("high")),
        "low": _safe_float(raw_row.get("low")),
        "close": _safe_float(raw_row.get("close")),
        "volume_shares": volume_shares,
        "volume_hands": volume_shares / 100 if volume_shares else 0.0,
    }


def _request_json(
    url: str,
    retries: int = 3,
    timeout: int = 5,
    raise_on_error: bool = False,
) -> Optional[List[Dict]]:
    last_error = "未知错误"

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if payload is None:
                raise RuntimeError("新浪接口返回空数据")
            if not isinstance(payload, list):
                raise RuntimeError("新浪接口返回格式异常")
            return payload
        except (requests.exceptions.RequestException, ValueError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))

    if raise_on_error:
        raise RuntimeError(last_error)
    return None


def get_history_kline(
    code: str,
    scale: int = 240,
    datalen: int = 120,
    retries: int = 3,
    timeout: int = 5,
    raise_on_error: bool = False,
) -> Optional[List[Dict]]:
    """
    获取历史 K 线数据。

    返回字段中：
    - volume_shares: 股
    - volume_hands: 手
    """
    try:
        symbol = get_market_symbol(code)
    except ValueError as exc:
        if raise_on_error:
            raise RuntimeError(str(exc)) from exc
        return None

    length = max(int(datalen), 1)
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&datalen={length}"
    )

    payload = _request_json(url, retries=retries, timeout=timeout, raise_on_error=raise_on_error)
    if payload is None:
        return None

    rows = []
    for raw_row in payload:
        normalized = _normalize_history_row(raw_row)
        if normalized:
            rows.append(normalized)

    rows.sort(key=lambda item: item["day"])
    if not rows and raise_on_error:
        raise RuntimeError("历史 K 线为空")
    return rows


if __name__ == "__main__":
    import json

    sample = get_history_kline("600867", datalen=5, raise_on_error=True)
    print(json.dumps(sample, indent=2, ensure_ascii=False))
