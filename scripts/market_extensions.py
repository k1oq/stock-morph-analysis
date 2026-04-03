#!/usr/bin/env python3
"""
东方财富扩展市场数据接口与分析工具。
"""
from __future__ import annotations

from datetime import datetime
import math
import time
from typing import Dict, List, Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
KLINE_URLS = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://63.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://33.push2his.eastmoney.com/api/qt/stock/kline/get",
)
FUND_FLOW_URLS = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
    "https://63.push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
)
ADJUST_MAP = {"qfq": "1", "hfq": "2", "": "0"}
CHIP_BUCKETS = 150
CHIP_LOOKBACK = 120


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
    timeout: int = 12,
    raise_on_error: bool = False,
) -> Optional[Dict]:
    last_error = "未知错误"

    for url in urls:
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
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


def fetch_market_activity_history(
    code: str,
    days: int = CHIP_LOOKBACK,
    adjust: str = "",
    raise_on_error: bool = False,
) -> List[Dict]:
    try:
        market_code = get_eastmoney_market_code(code)
    except ValueError as exc:
        if raise_on_error:
            raise RuntimeError(str(exc)) from exc
        return []

    payload = _request_json_from_candidates(
        KLINE_URLS,
        params={
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",
            "fqt": ADJUST_MAP.get(adjust, "0"),
            "secid": f"{market_code}.{str(code).strip()}",
            "end": datetime.now().strftime("%Y%m%d"),
            "lmt": str(max(int(days), CHIP_LOOKBACK)),
        },
        raise_on_error=raise_on_error,
    )
    data = payload.get("data") or {} if payload else {}
    klines = data.get("klines", [])
    rows: List[Dict] = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 11:
            continue
        volume_shares = _safe_float(parts[5])
        amount_yuan = _safe_float(parts[6])
        rows.append(
            {
                "date": parts[0],
                "open": _safe_float(parts[1]),
                "close": _safe_float(parts[2]),
                "high": _safe_float(parts[3]),
                "low": _safe_float(parts[4]),
                "volume_shares": volume_shares,
                "volume_hands": volume_shares / 100 if volume_shares else 0.0,
                "amount_yuan": amount_yuan,
                "amount_wan_yuan": amount_yuan / 10000 if amount_yuan else 0.0,
                "amount_yi_yuan": amount_yuan / 100000000 if amount_yuan else 0.0,
                "amplitude": _safe_float(parts[7]),
                "change_percent": _safe_float(parts[8]),
                "change_amount": _safe_float(parts[9]),
                "turnover_rate": _safe_float(parts[10]),
            }
        )

    if not rows and raise_on_error:
        raise RuntimeError(f"未获取到 {code} 的东财日线数据")
    return rows


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


def _average(rows: List[Dict], field: str, count: int, include_latest: bool = False) -> Optional[float]:
    if not rows:
        return None
    values_source = rows[-count:] if include_latest else rows[-(count + 1):-1]
    values = [float(row[field]) for row in values_source if row.get(field) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _ratio(value: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if value is None or baseline in (None, 0):
        return None
    return value / baseline


def _percent_distance(price: float, reference: Optional[float]) -> Optional[float]:
    if reference in (None, 0):
        return None
    return (price - float(reference)) / float(reference) * 100


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
    avg_volume_5 = _average(history_rows, "volume_hands", 5)
    avg_volume_20 = _average(history_rows, "volume_hands", 20)
    volume_ratio_5 = _ratio(latest_volume, avg_volume_5)
    volume_ratio_20 = _ratio(latest_volume, avg_volume_20)
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


def build_turnover_analysis(realtime: Dict, market_history_rows: List[Dict]) -> Dict:
    if len(market_history_rows) < 2:
        return {
            **_build_unavailable_result("换手率数据暂不可用"),
            "latest_date": None,
            "latest_turnover_rate": None,
            "average_turnover_rate_5": None,
            "average_turnover_rate_20": None,
            "turnover_ratio_5": None,
            "turnover_ratio_20": None,
            "activity_level": "不可用",
        }

    latest = market_history_rows[-1]
    latest_turnover = float(latest.get("turnover_rate", 0.0))
    avg_turnover_5 = _average(market_history_rows, "turnover_rate", 5)
    avg_turnover_20 = _average(market_history_rows, "turnover_rate", 20)
    ratio_5 = _ratio(latest_turnover, avg_turnover_5)
    ratio_20 = _ratio(latest_turnover, avg_turnover_20)
    price_change = float(realtime.get("change", latest.get("change_percent", 0.0)))

    if latest_turnover >= 12 or (ratio_20 or 0) >= 2.0:
        activity_level = "高换手"
    elif latest_turnover >= 5 or (ratio_20 or 0) >= 1.3:
        activity_level = "活跃"
    elif latest_turnover <= 1 and (ratio_20 or 1) <= 0.7:
        activity_level = "低换手"
    else:
        activity_level = "常态"

    if activity_level in {"高换手", "活跃"} and price_change > 0:
        signal = "偏多"
        description = "换手率抬升且价格走强，筹码交换积极，短线弹性较好。"
    elif activity_level in {"高换手", "活跃"} and price_change < 0:
        signal = "偏空"
        description = "换手放大但价格走弱，说明多空分歧加剧，需警惕高位派发。"
    else:
        signal = "中性"
        description = "换手率处于常态区间，市场参与热度暂未显著失衡。"

    return {
        "available": True,
        "latest_date": latest["date"],
        "latest_turnover_rate": round_float(latest_turnover, 2),
        "average_turnover_rate_5": round_float(avg_turnover_5, 2),
        "average_turnover_rate_20": round_float(avg_turnover_20, 2),
        "turnover_ratio_5": round_float(ratio_5, 2),
        "turnover_ratio_20": round_float(ratio_20, 2),
        "activity_level": activity_level,
        "signal": signal,
        "description": description,
    }


def _compute_chip_distribution(rows: List[Dict]) -> Optional[Dict]:
    if len(rows) < 20:
        return None

    max_price = max(float(row["high"]) for row in rows)
    min_price = min(float(row["low"]) for row in rows)
    accuracy = max(0.01, (max_price - min_price) / (CHIP_BUCKETS - 1))
    chips = [0.0] * CHIP_BUCKETS

    for row in rows:
        high = float(row["high"])
        low = float(row["low"])
        avg = (float(row["open"]) + float(row["close"]) + high + low) / 4
        turnover_rate = min(1.0, max(0.0, float(row.get("turnover_rate", 0.0)) / 100))

        retain_factor = 1 - turnover_rate
        for index, chip in enumerate(chips):
            chips[index] = chip * retain_factor

        if high <= low:
            grid_index = int(math.floor((avg - min_price) / accuracy)) if accuracy else 0
            grid_index = max(0, min(CHIP_BUCKETS - 1, grid_index))
            chips[grid_index] += (CHIP_BUCKETS - 1) * turnover_rate / 2
            continue

        upper = max(0, min(CHIP_BUCKETS - 1, int(math.floor((high - min_price) / accuracy))))
        lower = max(0, min(CHIP_BUCKETS - 1, int(math.ceil((low - min_price) / accuracy))))
        slope = 2 / (high - low)

        for grid_index in range(lower, upper + 1):
            current_price = min_price + accuracy * grid_index
            if current_price <= avg:
                if abs(avg - low) < 1e-8:
                    chips[grid_index] += slope * turnover_rate
                else:
                    chips[grid_index] += (current_price - low) / (avg - low) * slope * turnover_rate
            else:
                if abs(high - avg) < 1e-8:
                    chips[grid_index] += slope * turnover_rate
                else:
                    chips[grid_index] += (high - current_price) / (high - avg) * slope * turnover_rate

    total_chips = sum(max(chip, 0.0) for chip in chips)
    if total_chips <= 0:
        return None
    return {
        "chips": [max(chip, 0.0) for chip in chips],
        "total_chips": total_chips,
        "min_price": min_price,
        "accuracy": accuracy,
    }


def _get_cost_by_chip(chips: List[float], total_chips: float, min_price: float, accuracy: float, percent: float) -> float:
    target = total_chips * percent
    cumulative = 0.0
    for index, chip in enumerate(chips):
        if cumulative + chip > target:
            return round(min_price + accuracy * index, 2)
        cumulative += chip
    return round(min_price + accuracy * (len(chips) - 1), 2)


def _build_percent_chip_range(
    chips: List[float],
    total_chips: float,
    min_price: float,
    accuracy: float,
    percent: float,
) -> Dict:
    low_cost = _get_cost_by_chip(chips, total_chips, min_price, accuracy, (1 - percent) / 2)
    high_cost = _get_cost_by_chip(chips, total_chips, min_price, accuracy, (1 + percent) / 2)
    concentration = ((high_cost - low_cost) / (high_cost + low_cost) * 100) if (high_cost + low_cost) else 0.0
    return {
        "low": round_float(low_cost, 2),
        "high": round_float(high_cost, 2),
        "concentration": round_float(concentration, 2),
    }


def build_chip_distribution_analysis(price: float, market_history_rows: List[Dict]) -> Dict:
    latest_rows = market_history_rows[-CHIP_LOOKBACK:]
    chip_payload = _compute_chip_distribution(latest_rows)
    if chip_payload is None:
        return {
            **_build_unavailable_result("历史换手与价格数据不足，无法计算筹码分布"),
            "latest_date": market_history_rows[-1]["date"] if market_history_rows else None,
            "profit_ratio": None,
            "average_cost": None,
            "distance_to_average_cost_percent": None,
            "cost_range_70": None,
            "cost_range_90": None,
            "price_position": "不可用",
        }

    chips = chip_payload["chips"]
    total_chips = chip_payload["total_chips"]
    min_price = chip_payload["min_price"]
    accuracy = chip_payload["accuracy"]

    profitable_chips = 0.0
    for index, chip in enumerate(chips):
        current_price = min_price + accuracy * index
        if current_price <= price:
            profitable_chips += chip
    profit_ratio = profitable_chips / total_chips * 100

    average_cost = _get_cost_by_chip(chips, total_chips, min_price, accuracy, 0.5)
    cost_range_70 = _build_percent_chip_range(chips, total_chips, min_price, accuracy, 0.7)
    cost_range_90 = _build_percent_chip_range(chips, total_chips, min_price, accuracy, 0.9)
    distance_to_cost = _percent_distance(price, average_cost)

    if price > cost_range_90["high"]:
        price_position = "突破 90% 成本上沿"
    elif price < cost_range_90["low"]:
        price_position = "跌破 90% 成本下沿"
    elif cost_range_70["low"] <= price <= cost_range_70["high"]:
        price_position = "位于 70% 成本密集区"
    else:
        price_position = "位于 90% 成本区间内"

    concentration_90 = cost_range_90["concentration"] or 0.0
    if price >= average_cost and profit_ratio >= 60 and concentration_90 <= 15:
        signal = "偏多"
        description = "现价位于主要成本上方，获利盘占比较高且筹码相对集中。"
    elif price < average_cost and profit_ratio <= 40 and concentration_90 >= 18:
        signal = "偏空"
        description = "现价落在平均成本下方，获利盘偏少且成本带分散，抛压消化仍需时间。"
    else:
        signal = "中性"
        description = "筹码结构没有出现明显单边优势，需要结合趋势与资金流继续确认。"

    return {
        "available": True,
        "latest_date": latest_rows[-1]["date"],
        "profit_ratio": round_float(profit_ratio, 2),
        "average_cost": round_float(average_cost, 2),
        "distance_to_average_cost_percent": round_float(distance_to_cost, 2),
        "cost_range_70": cost_range_70,
        "cost_range_90": cost_range_90,
        "price_position": price_position,
        "signal": signal,
        "description": description,
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
