#!/usr/bin/env python3
"""
扩展市场数据接口与分析工具。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
FUND_FLOW_URLS = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
    "https://63.push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
)


def round_float(value: Optional[float], digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_unavailable_result(description: str) -> Dict:
    return {
        "available": False,
        "signal": "不可用",
        "description": description,
    }


def get_eastmoney_market_code(code: str) -> int:
    normalized = str(code).strip()
    if not normalized:
        raise ValueError("股票代码不能为空")
    return 1 if normalized.startswith("6") else 0


def _request_json_from_candidates(
    urls: tuple[str, ...],
    params: Dict[str, str],
    retries: int = 5,
    raise_on_error: bool = False,
) -> Optional[Dict]:
    last_error = "未知错误"

    for url in urls:
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, headers=DEFAULT_HEADERS)
                response.raise_for_status()
                payload = response.json()
                if payload is None or "data" not in payload:
                    raise RuntimeError("接口返回格式异常")
                return payload
            except (requests.exceptions.RequestException, ValueError, RuntimeError) as exc:
                last_error = str(exc)
                if attempt < retries - 1:
                    time.sleep(0.8 * (attempt + 1))

    if raise_on_error:
        raise RuntimeError(last_error)
    return None


def fetch_individual_fund_flow_history(
    code: str,
    days: int = 120,
    raise_on_error: bool = False,
) -> List[Dict]:
    try:
        market_code = get_eastmoney_market_code(code)
    except ValueError as exc:
        if raise_on_error:
            raise RuntimeError(str(exc)) from exc
        return []

    payload = _request_json_from_candidates(
        FUND_FLOW_URLS,
        params={
            "lmt": str(max(int(days), 30)),
            "klt": "101",
            "secid": f"{market_code}.{str(code).strip()}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "_": str(int(time.time() * 1000)),
        },
        raise_on_error=raise_on_error,
    )
    data = payload.get("data") or {} if payload else {}
    klines = data.get("klines", [])
    rows: List[Dict] = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 13:
            continue

        main_net_inflow = _safe_float(parts[1])
        rows.append(
            {
                "date": parts[0],
                "main_net_inflow_yuan": main_net_inflow,
                "main_net_inflow_yi_yuan": main_net_inflow / 100000000 if main_net_inflow else 0.0,
                "small_net_inflow_yuan": _safe_float(parts[2]),
                "medium_net_inflow_yuan": _safe_float(parts[3]),
                "large_net_inflow_yuan": _safe_float(parts[4]),
                "super_large_net_inflow_yuan": _safe_float(parts[5]),
                "main_net_inflow_ratio": _safe_float(parts[6]),
                "small_net_inflow_ratio": _safe_float(parts[7]),
                "medium_net_inflow_ratio": _safe_float(parts[8]),
                "large_net_inflow_ratio": _safe_float(parts[9]),
                "super_large_net_inflow_ratio": _safe_float(parts[10]),
                "close": _safe_float(parts[11]),
                "change_percent": _safe_float(parts[12]),
            }
        )

    if not rows and raise_on_error:
        raise RuntimeError(f"未获取到 {code} 的资金流向数据")
    return rows


def _average(rows: List[Dict], field: str, count: int) -> Optional[float]:
    if not rows:
        return None
    values = [float(row[field]) for row in rows[-count:] if row.get(field) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def build_volume_profile(realtime: Dict, history_rows: List[Dict]) -> Dict:
    if len(history_rows) < 6:
        return {
            **_build_unavailable_result("历史成交量不足，无法分析近 5 日量能变化"),
            "latest_date": history_rows[-1]["day"] if history_rows else None,
            "latest_volume_wan_hands": None,
            "average_volume_wan_hands_5": None,
            "average_volume_wan_hands_20": None,
            "volume_ratio_5": None,
            "volume_ratio_20": None,
            "amount_yi_yuan": round_float(realtime.get("amount_yi_yuan"), 2),
        }

    latest_row = history_rows[-1]
    latest_volume = float(latest_row.get("volume_hands", 0.0))
    avg_volume_5 = _average(history_rows[:-1], "volume_hands", 5)
    avg_volume_20 = _average(history_rows[:-1], "volume_hands", 20)
    volume_ratio_5 = latest_volume / avg_volume_5 if avg_volume_5 else None
    volume_ratio_20 = latest_volume / avg_volume_20 if avg_volume_20 else None
    price_change = float(realtime.get("change", 0.0))

    if (volume_ratio_5 or 0) >= 1.6 and price_change > 0:
        signal = "偏多"
        volume_state = "明显放量"
        description = "近端量能显著放大，价格同步上行，短线资金参与度较高。"
    elif (volume_ratio_5 or 0) >= 1.3 and price_change < 0:
        signal = "偏空"
        volume_state = "放量分歧"
        description = "成交量放大但价格走弱，说明抛压释放较明显。"
    elif (volume_ratio_5 or 0) <= 0.75:
        signal = "中性"
        volume_state = "缩量"
        description = "近端量能低于常态，短线更多处于等待与博弈阶段。"
    else:
        signal = "中性"
        volume_state = "常态"
        description = "量能大体维持常态，更多需要结合趋势和形态判断。"

    return {
        "available": True,
        "latest_date": latest_row["day"],
        "latest_volume_wan_hands": round_float(latest_volume / 10000, 2),
        "average_volume_wan_hands_5": round_float(avg_volume_5 / 10000 if avg_volume_5 else None, 2),
        "average_volume_wan_hands_20": round_float(avg_volume_20 / 10000 if avg_volume_20 else None, 2),
        "volume_ratio_5": round_float(volume_ratio_5, 2),
        "volume_ratio_20": round_float(volume_ratio_20, 2),
        "amount_yi_yuan": round_float(realtime.get("amount_yi_yuan"), 2),
        "volume_state": volume_state,
        "signal": signal,
        "description": description,
    }


def build_turnover_analysis(realtime: Dict) -> Dict:
    turnover_rate = realtime.get("turnover_rate")
    if turnover_rate in (None, ""):
        return {
            **_build_unavailable_result("腾讯财经未返回当前换手率"),
            "latest_date": None,
            "latest_turnover_rate": None,
            "average_turnover_rate_5": None,
            "average_turnover_rate_20": None,
            "turnover_ratio_5": None,
            "turnover_ratio_20": None,
            "activity_level": "不可用",
            "source": "tencent_realtime",
        }

    latest_turnover = float(turnover_rate)
    price_change = float(realtime.get("change", 0.0))
    timestamp = str(realtime.get("timestamp") or "")
    latest_date = timestamp.split(" ", 1)[0] if timestamp else None

    if latest_turnover >= 12:
        activity_level = "高换手"
    elif latest_turnover >= 5:
        activity_level = "活跃"
    elif latest_turnover <= 1:
        activity_level = "低换手"
    else:
        activity_level = "常态"

    if activity_level in {"高换手", "活跃"} and price_change > 0:
        signal = "偏多"
        description = "腾讯财经实时换手率显示市场参与度较高，价格同步走强。"
    elif activity_level in {"高换手", "活跃"} and price_change < 0:
        signal = "偏空"
        description = "腾讯财经实时换手率偏高，但价格走弱，短线分歧较大。"
    else:
        signal = "中性"
        description = "当前换手率处于常态区间，可结合量能与趋势继续观察。"

    return {
        "available": True,
        "latest_date": latest_date,
        "latest_turnover_rate": round_float(latest_turnover, 2),
        "average_turnover_rate_5": None,
        "average_turnover_rate_20": None,
        "turnover_ratio_5": None,
        "turnover_ratio_20": None,
        "activity_level": activity_level,
        "signal": signal,
        "description": description,
        "source": "tencent_realtime",
    }


def build_fund_flow_analysis(fund_flow_rows: List[Dict]) -> Dict:
    if not fund_flow_rows:
        return {
            **_build_unavailable_result("主力资金流向数据暂不可用"),
            "latest_date": None,
            "main_net_inflow_yi_yuan": None,
            "main_net_inflow_ratio": None,
            "cumulative_main_net_inflow_3d_yi_yuan": None,
            "cumulative_main_net_inflow_5d_yi_yuan": None,
        }

    latest = fund_flow_rows[-1]
    last_3_rows = fund_flow_rows[-3:]
    last_5_rows = fund_flow_rows[-5:]
    cumulative_3d = sum(float(row.get("main_net_inflow_yuan", 0.0)) for row in last_3_rows) / 100000000
    cumulative_5d = sum(float(row.get("main_net_inflow_yuan", 0.0)) for row in last_5_rows) / 100000000
    latest_ratio = float(latest.get("main_net_inflow_ratio", 0.0))

    if latest_ratio >= 5 and cumulative_5d > 0:
        signal = "偏多"
        description = "主力资金最近 5 日维持净流入，且当日净占比处于较高水平。"
    elif latest_ratio <= -5 and cumulative_5d < 0:
        signal = "偏空"
        description = "主力资金最近 5 日持续净流出，短线承接偏弱。"
    else:
        signal = "中性"
        description = "主力资金进出尚未形成连续单边结构，更多表现为震荡换手。"

    return {
        "available": True,
        "latest_date": latest["date"],
        "close": round_float(latest.get("close"), 2),
        "change_percent": round_float(latest.get("change_percent"), 2),
        "main_net_inflow_yi_yuan": round_float(latest.get("main_net_inflow_yi_yuan"), 2),
        "main_net_inflow_ratio": round_float(latest_ratio, 2),
        "super_large_net_inflow_yi_yuan": round_float(
            float(latest.get("super_large_net_inflow_yuan", 0.0)) / 100000000,
            2,
        ),
        "large_net_inflow_yi_yuan": round_float(float(latest.get("large_net_inflow_yuan", 0.0)) / 100000000, 2),
        "medium_net_inflow_yi_yuan": round_float(
            float(latest.get("medium_net_inflow_yuan", 0.0)) / 100000000,
            2,
        ),
        "small_net_inflow_yi_yuan": round_float(float(latest.get("small_net_inflow_yuan", 0.0)) / 100000000, 2),
        "cumulative_main_net_inflow_3d_yi_yuan": round_float(cumulative_3d, 2),
        "cumulative_main_net_inflow_5d_yi_yuan": round_float(cumulative_5d, 2),
        "signal": signal,
        "description": description,
    }
