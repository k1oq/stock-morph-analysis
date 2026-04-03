#!/usr/bin/env python3
"""
A 股形态学分析工具主程序。

使用方法:
    python3 scripts/morph_analyzer.py --code 600867
    python3 scripts/morph_analyzer.py --code 600867 --detailed
    python3 scripts/morph_analyzer.py --code 600867 --json
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional

from indicators import calc_bollinger, calc_ma, calc_macd, calc_rsi, get_rsi_signal
from market_extensions import (
    build_chip_distribution_analysis,
    build_fund_flow_analysis,
    build_turnover_analysis,
    build_volume_profile,
    fetch_individual_fund_flow_history,
    fetch_market_activity_history,
)
from patterns import identify_engulfing_pattern, identify_single_pattern
from sina_history import get_history_kline
from tencent_api import get_realtime_data


LINE_WIDTH = 66
WATCHLIST_SORT_LABELS = {
    "score": "评分",
    "change": "涨跌幅",
}
WATCHLIST_CSV_COLUMNS = (
    ("rank", "排名"),
    ("code", "代码"),
    ("name", "名称"),
    ("price", "最新价"),
    ("change_percent", "涨跌幅(%)"),
    ("score", "评分"),
    ("signal", "评分结论"),
    ("action", "操作建议"),
    ("warning_count", "警告数"),
    ("history_status", "历史数据"),
    ("indicator_status", "指标数据"),
    ("generated_at", "生成时间"),
)
ICON_MAP = {
    True: {
        "bullish": "🟢",
        "bearish": "🔴",
        "neutral": "⚪",
        "title": "📊",
        "warning": "⚠️",
    },
    False: {
        "bullish": "[+]",
        "bearish": "[-]",
        "neutral": "[=]",
        "title": "",
        "warning": "!",
    },
}


def supports_unicode_output() -> bool:
    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


def get_icon(name: str) -> str:
    return ICON_MAP[supports_unicode_output()][name]


def round_float(value: Optional[float], digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def percent_distance(price: float, reference: Optional[float]) -> Optional[float]:
    if reference in (None, 0):
        return None
    return round_float((price - float(reference)) / float(reference) * 100, 2)


def analyze_volume_price(volume_ratio: Optional[float], price_change: float) -> Dict:
    """
    分析量价关系。
    """
    if volume_ratio is None:
        return {
            "volume_ratio": None,
            "relation": "不可用",
            "signal": "中性",
            "description": "历史成交量不足，无法计算量比",
            "score": 0.0,
            "icon": "neutral",
        }

    if volume_ratio >= 1.5 and price_change > 0:
        return {
            "volume_ratio": round_float(volume_ratio, 2),
            "relation": "量增价升",
            "signal": "偏多",
            "description": "资金流入明显，多头信号",
            "score": 1.0,
            "icon": "bullish",
        }
    if volume_ratio >= 1.2 and price_change > 0:
        return {
            "volume_ratio": round_float(volume_ratio, 2),
            "relation": "量增价升",
            "signal": "偏多",
            "description": "放量上涨，趋势延续概率较高",
            "score": 0.8,
            "icon": "bullish",
        }
    if volume_ratio >= 1.5 and price_change < 0:
        return {
            "volume_ratio": round_float(volume_ratio, 2),
            "relation": "放量下跌",
            "signal": "偏空",
            "description": "抛压较重，空头占优",
            "score": -1.0,
            "icon": "bearish",
        }
    if volume_ratio >= 1.2 and price_change < 0:
        return {
            "volume_ratio": round_float(volume_ratio, 2),
            "relation": "放量下跌",
            "signal": "偏空",
            "description": "放量回落，注意短线风险",
            "score": -0.8,
            "icon": "bearish",
        }
    if volume_ratio <= 0.8 and price_change > 0:
        return {
            "volume_ratio": round_float(volume_ratio, 2),
            "relation": "缩量上涨",
            "signal": "中性偏多",
            "description": "上涨动能一般，继续观察能否补量",
            "score": 0.2,
            "icon": "neutral",
        }
    if volume_ratio <= 0.8 and price_change < 0:
        return {
            "volume_ratio": round_float(volume_ratio, 2),
            "relation": "缩量下跌",
            "signal": "中性偏空",
            "description": "抛压减弱，下跌动能有所缓和",
            "score": -0.2,
            "icon": "neutral",
        }

    return {
        "volume_ratio": round_float(volume_ratio, 2),
        "relation": "震荡整理",
        "signal": "中性",
        "description": "量价配合一般，市场仍在博弈",
        "score": 0.0,
        "icon": "neutral",
    }


def get_score_signal(score: float) -> str:
    if score >= 4:
        return "强烈看多"
    if score >= 2:
        return "偏多"
    if score >= 0.5:
        return "中性偏多"
    if score > -0.5:
        return "中性"
    if score > -2:
        return "偏空"
    return "强烈看空"


def determine_ma_arrangement(price: float, ma_values: Dict[str, Optional[float]]) -> Dict:
    ma5 = ma_values.get("ma5")
    ma10 = ma_values.get("ma10")
    ma20 = ma_values.get("ma20")
    ma60 = ma_values.get("ma60")

    if None in (ma5, ma10, ma20, ma60):
        return {"name": "不可用", "signal": "历史数据不足"}

    if ma5 > ma10 > ma20 > ma60 and price > ma5:
        return {"name": "多头排列", "signal": "趋势偏强"}
    if ma5 < ma10 < ma20 < ma60 and price < ma5:
        return {"name": "空头排列", "signal": "趋势偏弱"}
    return {"name": "震荡修复", "signal": "均线尚未形成单边趋势"}


def describe_bollinger_position(price: float, bollinger: Dict[str, Optional[float]]) -> str:
    upper = bollinger.get("upper")
    middle = bollinger.get("middle")
    lower = bollinger.get("lower")
    if None in (upper, middle, lower):
        return "不可用"

    band = upper - lower
    if band <= 0:
        return "不可用"

    if price >= upper:
        return "上轨上方"
    if price >= upper - band * 0.1:
        return "上轨附近"
    if price >= middle:
        return "中轨上方"
    if price <= lower:
        return "下轨下方"
    if price <= lower + band * 0.1:
        return "下轨附近"
    return "中轨下方"


def calc_trend_score(price: float, moving_averages: Dict) -> float:
    ma20 = moving_averages["ma20"]["value"]
    ma60 = moving_averages["ma60"]["value"]
    arrangement = moving_averages["arrangement"]["name"]

    if ma20 is None or ma60 is None:
        return 0.0
    if arrangement == "多头排列" and price > ma20 > ma60:
        return 1.5
    if price > ma20 and price > ma60:
        return 1.0
    if price > ma20:
        return 0.5
    if arrangement == "空头排列" and price < ma20 < ma60:
        return -1.5
    if price < ma20 and price < ma60:
        return -1.0
    if price < ma20:
        return -0.5
    return 0.0


def calc_momentum_score(price: float, indicators: Dict) -> float:
    macd = indicators["macd"]
    rsi = indicators["rsi"]["value"]
    bollinger = indicators["bollinger"]

    if macd["signal"] == "数据不足" or rsi is None or bollinger["upper"] is None:
        return 0.0

    score = 0.0
    if macd["signal"] in {"金叉", "多头上行"}:
        score += 0.5
    elif macd["signal"] in {"死叉", "空头下行"}:
        score -= 0.5

    if rsi >= 80:
        score -= 0.1
    elif rsi >= 65:
        score += 0.35
    elif rsi >= 55:
        score += 0.2
    elif rsi <= 20:
        score += 0.1
    elif rsi <= 35:
        score -= 0.35
    elif rsi < 45:
        score -= 0.2

    boll_position = describe_bollinger_position(price, bollinger)
    if boll_position in {"上轨上方", "上轨附近"}:
        score += 0.15
    elif boll_position == "中轨上方":
        score += 0.05
    elif boll_position == "中轨下方":
        score -= 0.05
    elif boll_position in {"下轨附近", "下轨下方"}:
        score -= 0.15

    return max(-1.0, min(1.0, round_float(score, 2)))


def calc_pattern_score(kline_pattern: Dict) -> float:
    engulfing = kline_pattern["engulfing"]
    single = kline_pattern["single"]

    if engulfing["score"] != 0:
        return engulfing["score"]

    pattern_type = single["type"]
    if pattern_type in {"大阳线", "中阳线", "锤子线"}:
        return 0.3
    if pattern_type in {"大阴线", "中阴线", "倒锤子"}:
        return -0.3
    return 0.0


def get_round_step(price: float) -> float:
    if price < 20:
        return 1.0
    if price < 100:
        return 5.0
    if price < 500:
        return 10.0
    if price < 2000:
        return 50.0
    return 100.0


def _merge_level(levels: Dict[float, Dict], price: Optional[float], source: str) -> None:
    if price is None or price <= 0:
        return

    rounded_price = round(float(price), 2)
    if rounded_price in levels:
        existing_sources = levels[rounded_price]["source"].split(" / ")
        if source not in existing_sources:
            existing_sources.append(source)
            levels[rounded_price]["source"] = " / ".join(existing_sources)
        return

    levels[rounded_price] = {"price": rounded_price, "source": source}


def calc_support_resistance(realtime: Dict, history_rows: List[Dict], moving_averages: Dict) -> Dict:
    """
    计算支撑位与压力位。
    """
    current_price = realtime["price"]
    resistance_levels: Dict[float, Dict] = {}
    support_levels: Dict[float, Dict] = {}

    _merge_level(resistance_levels, realtime.get("high"), "今日最高")
    _merge_level(support_levels, realtime.get("low"), "今日最低")

    recent_window = history_rows[-20:] if history_rows else []
    if recent_window:
        recent_high = max(row["high"] for row in recent_window)
        recent_low = min(row["low"] for row in recent_window)
        if recent_high >= current_price:
            _merge_level(resistance_levels, recent_high, "20日高点")
        if recent_low <= current_price:
            _merge_level(support_levels, recent_low, "20日低点")

    for label in ("ma5", "ma10", "ma20", "ma60"):
        value = moving_averages.get(label, {}).get("value")
        if value is None:
            continue
        if value >= current_price:
            _merge_level(resistance_levels, value, label.upper())
        if value <= current_price:
            _merge_level(support_levels, value, label.upper())

    step = get_round_step(current_price)
    upper_round = math.ceil(current_price / step) * step
    lower_round = math.floor(current_price / step) * step
    if upper_round >= current_price:
        _merge_level(resistance_levels, upper_round, "整数关口")
    if lower_round <= current_price:
        _merge_level(support_levels, lower_round, "整数关口")

    resistances = sorted(
        [level for level in resistance_levels.values() if level["price"] >= current_price],
        key=lambda item: item["price"],
    )[:3]
    supports = sorted(
        [level for level in support_levels.values() if level["price"] <= current_price],
        key=lambda item: item["price"],
        reverse=True,
    )[:3]

    return {"resistance": resistances, "support": supports}


def merge_history_with_realtime(history_rows: List[Dict], realtime: Dict) -> List[Dict]:
    """
    用实时数据覆盖或追加当日 K 线，使盘中分析更贴近实时。
    """
    merged = list(history_rows)
    today = datetime.now().strftime("%Y-%m-%d")
    today_row = {
        "day": today,
        "open": realtime["open"],
        "high": realtime["high"],
        "low": realtime["low"],
        "close": realtime["price"],
        "volume_shares": realtime["volume_shares"],
        "volume_hands": realtime["volume_hands"],
    }

    if merged and merged[-1]["day"] == today:
        merged[-1] = today_row
    else:
        merged.append(today_row)
    return merged


def build_moving_averages(price: float, close_prices: List[float]) -> Dict:
    result = {}
    periods = (5, 10, 20, 60)
    ma_values: Dict[str, Optional[float]] = {}

    for period in periods:
        key = f"ma{period}"
        if len(close_prices) >= period:
            value = round_float(calc_ma(close_prices, period), 4)
        else:
            value = None
        ma_values[key] = value
        result[key] = {
            "value": value,
            "distance_percent": percent_distance(price, value),
        }

    result["arrangement"] = determine_ma_arrangement(price, ma_values)
    return result


def build_indicators(price: float, close_prices: List[float]) -> Dict:
    if len(close_prices) < 35:
        return {
            "macd": {
                "dif": None,
                "dea": None,
                "macd": None,
                "signal": "数据不足",
            },
            "rsi": {
                "value": None,
                "signal": "历史数据不足",
            },
            "bollinger": {
                "upper": None,
                "middle": None,
                "lower": None,
                "bandwidth": None,
                "position": "不可用",
            },
        }

    macd_raw = calc_macd(close_prices)
    rsi_value = round_float(calc_rsi(close_prices), 2)
    bollinger_raw = calc_bollinger(close_prices)

    bollinger = {
        "upper": round_float(bollinger_raw["upper"], 4),
        "middle": round_float(bollinger_raw["middle"], 4),
        "lower": round_float(bollinger_raw["lower"], 4),
        "bandwidth": round_float(bollinger_raw["bandwidth"], 2),
    }
    bollinger["position"] = describe_bollinger_position(price, bollinger)

    return {
        "macd": {
            "dif": round_float(macd_raw["dif"], 4),
            "dea": round_float(macd_raw["dea"], 4),
            "macd": round_float(macd_raw["macd"], 4),
            "signal": macd_raw["signal"],
        },
        "rsi": {
            "value": rsi_value,
            "signal": get_rsi_signal(rsi_value),
        },
        "bollinger": bollinger,
    }


def build_volume_ratio(history_rows: List[Dict]) -> Optional[float]:
    if len(history_rows) < 6:
        return None

    current_volume = history_rows[-1]["volume_shares"]
    previous_volumes = [row["volume_shares"] for row in history_rows[-6:-1] if row["volume_shares"] > 0]
    if len(previous_volumes) < 5:
        return None

    average_volume = sum(previous_volumes) / len(previous_volumes)
    if average_volume <= 0:
        return None
    return current_volume / average_volume


def build_kline_pattern(realtime: Dict, history_rows: List[Dict]) -> Dict:
    single = identify_single_pattern(
        realtime["open"],
        realtime["price"],
        realtime["high"],
        realtime["low"],
    )

    engulfing = {
        "type": "无",
        "signal": "",
        "reliability": "低",
        "score": 0.0,
        "bias": "neutral",
    }
    if len(history_rows) >= 2:
        today = history_rows[-1]
        yesterday = history_rows[-2]
        engulfing = identify_engulfing_pattern(today, yesterday)

    return {"single": single, "engulfing": engulfing}


def build_advice(total_score: float, support_resistance: Dict, score_signal: str) -> Dict:
    support = support_resistance["support"][0]["price"] if support_resistance["support"] else None
    resistance = support_resistance["resistance"][0]["price"] if support_resistance["resistance"] else None

    if total_score >= 2.5:
        action = "持股待涨"
        rationale = "趋势与动能共振，保持顺势思路。"
    elif total_score >= 0.5:
        action = "持股观察"
        rationale = "技术面偏暖，但仍需观察量能持续性。"
    elif total_score <= -2.5:
        action = "减仓观望"
        rationale = "评分偏弱，优先控制回撤。"
    else:
        action = "观望等待"
        rationale = "信号分化，等待更明确的方向。"

    return {
        "action": action,
        "stop_loss": support,
        "target": resistance,
        "signal": score_signal,
        "rationale": rationale,
    }


def load_watchlist_codes(path: str) -> List[str]:
    watchlist_path = Path(path)
    try:
        content = watchlist_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RuntimeError(f"读取自选股文件失败：{exc}") from exc

    codes: List[str] = []
    seen = set()
    for raw_line in content.splitlines():
        cleaned_line = raw_line.split("#", 1)[0].strip()
        if not cleaned_line:
            continue

        for token in re.split(r"[\s,，;；]+", cleaned_line):
            code = token.strip()
            if not code or code in seen:
                continue
            seen.add(code)
            codes.append(code)

    if not codes:
        raise RuntimeError(f"自选股文件为空：{path}")
    return codes


def build_watchlist_summary_entry(analysis_result: Dict) -> Dict:
    meta = analysis_result["meta"]
    realtime = analysis_result["realtime"]
    score = analysis_result["score"]
    advice = analysis_result["advice"]
    data_status = analysis_result["data_status"]

    return {
        "code": meta["code"],
        "name": meta["name"],
        "price": realtime["price"],
        "change_percent": realtime["change_percent"],
        "score": score["total"],
        "signal": score["signal"],
        "action": advice["action"],
        "warning_count": len(analysis_result["warnings"]),
        "history_status": data_status["history"],
        "indicator_status": data_status["indicators"],
        "generated_at": meta["generated_at"],
    }


def sort_watchlist_summary(
    entries: List[Dict],
    sort_by: str = "score",
    descending: bool = True,
) -> List[Dict]:
    if sort_by not in WATCHLIST_SORT_LABELS:
        raise ValueError(f"不支持的排序字段：{sort_by}")

    if sort_by == "change":
        key_fn = lambda item: (item["change_percent"], item["score"], item["code"])
    else:
        key_fn = lambda item: (item["score"], item["change_percent"], item["code"])

    return sorted(entries, key=key_fn, reverse=descending)


def build_watchlist_analysis_result(
    codes: List[str],
    days: int = 30,
    sort_by: str = "score",
    descending: bool = True,
    source: Optional[str] = None,
) -> Dict:
    normalized_codes: List[str] = []
    seen = set()
    for raw_code in codes:
        code = str(raw_code).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        normalized_codes.append(code)

    if not normalized_codes:
        raise RuntimeError("自选股列表为空")

    results: List[Dict] = []
    summary_entries: List[Dict] = []
    failures: List[Dict] = []

    for code in normalized_codes:
        try:
            analysis_result = build_analysis_result(code, days=days)
        except RuntimeError as exc:
            failures.append({"code": code, "error": str(exc)})
            continue

        results.append(analysis_result)
        summary_entries.append(build_watchlist_summary_entry(analysis_result))

    sorted_summary = sort_watchlist_summary(summary_entries, sort_by=sort_by, descending=descending)
    ranked_summary = []
    for index, item in enumerate(sorted_summary, start=1):
        ranked_item = dict(item)
        ranked_item["rank"] = index
        ranked_summary.append(ranked_item)

    rank_by_code = {item["code"]: item["rank"] for item in ranked_summary}
    sorted_results = sorted(results, key=lambda item: rank_by_code.get(item["meta"]["code"], sys.maxsize))

    return {
        "meta": {
            "mode": "watchlist",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "analysis_days": days,
            "source": source,
            "requested": len(normalized_codes),
            "completed": len(ranked_summary),
            "failed": len(failures),
            "sort_by": sort_by,
            "sort_order": "desc" if descending else "asc",
        },
        "codes": normalized_codes,
        "summary": ranked_summary,
        "results": sorted_results,
        "failures": failures,
    }


def build_analysis_result(code: str, days: int = 30) -> Dict:
    realtime = get_realtime_data(code, raise_on_error=True)
    warnings: List[str] = []
    history_rows: List[Dict] = []
    market_history_rows: List[Dict] = []
    fund_flow_rows: List[Dict] = []

    data_status = {
        "realtime": "complete",
        "history": "degraded",
        "indicators": "degraded",
        "volume_profile": "degraded",
        "turnover": "degraded",
        "chip_distribution": "degraded",
        "fund_flow": "degraded",
    }

    try:
        raw_history = get_history_kline(code, scale=240, datalen=max(days, 120), raise_on_error=True)
        history_rows = merge_history_with_realtime(raw_history, realtime)
        data_status["history"] = "complete"
    except RuntimeError as exc:
        warnings.append(f"历史 K 线获取失败，已降级为实时分析：{exc}")

    close_prices = [row["close"] for row in history_rows]
    volume_ratio = build_volume_ratio(history_rows) if history_rows else None
    volume_price = analyze_volume_price(volume_ratio, realtime["change"])
    moving_averages = build_moving_averages(realtime["price"], close_prices) if history_rows else {
        "ma5": {"value": None, "distance_percent": None},
        "ma10": {"value": None, "distance_percent": None},
        "ma20": {"value": None, "distance_percent": None},
        "ma60": {"value": None, "distance_percent": None},
        "arrangement": {"name": "不可用", "signal": "历史数据不足"},
    }

    indicators = build_indicators(realtime["price"], close_prices) if history_rows else {
        "macd": {"dif": None, "dea": None, "macd": None, "signal": "数据不足"},
        "rsi": {"value": None, "signal": "历史数据不足"},
        "bollinger": {
            "upper": None,
            "middle": None,
            "lower": None,
            "bandwidth": None,
            "position": "不可用",
        },
    }
    if indicators["macd"]["signal"] != "数据不足":
        data_status["indicators"] = "complete"
    elif history_rows:
        warnings.append("历史 K 线数量不足，部分指标无法计算。")

    try:
        market_history_rows = fetch_market_activity_history(
            code,
            days=max(days, 120),
            raise_on_error=True,
        )
    except RuntimeError as exc:
        warnings.append(f"换手率与筹码分布获取失败，已跳过扩展分析：{exc}")

    try:
        fund_flow_rows = fetch_individual_fund_flow_history(
            code,
            days=max(days, 30),
            raise_on_error=True,
        )
    except RuntimeError as exc:
        warnings.append(f"主力资金流向获取失败，已跳过资金流分析：{exc}")

    volume_profile = build_volume_profile(realtime, history_rows)
    if volume_profile["available"]:
        data_status["volume_profile"] = "complete"

    turnover_analysis = build_turnover_analysis(realtime, market_history_rows)
    if turnover_analysis["available"]:
        data_status["turnover"] = "complete"

    chip_distribution = build_chip_distribution_analysis(realtime["price"], market_history_rows)
    if chip_distribution["available"]:
        data_status["chip_distribution"] = "complete"

    fund_flow = build_fund_flow_analysis(fund_flow_rows)
    if fund_flow["available"]:
        data_status["fund_flow"] = "complete"

    kline_pattern = build_kline_pattern(realtime, history_rows)

    trend_score = calc_trend_score(realtime["price"], moving_averages)
    momentum_score = calc_momentum_score(realtime["price"], indicators)
    volume_score = volume_price["score"]
    pattern_score = calc_pattern_score(kline_pattern)
    total_score = max(-5.0, min(5.0, trend_score + momentum_score + volume_score + pattern_score))
    total_score = round_float(total_score, 2)
    score_signal = get_score_signal(total_score)

    support_resistance = calc_support_resistance(realtime, history_rows, moving_averages)
    advice = build_advice(total_score, support_resistance, score_signal)

    return {
        "meta": {
            "code": realtime["code"],
            "name": realtime["name"],
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "analysis_days": days,
            "history_bars": len(history_rows),
        },
        "data_status": data_status,
        "warnings": warnings,
        "realtime": {
            "price": round_float(realtime["price"], 2),
            "change_percent": round_float(realtime["change"], 2),
            "change_amount": round_float(realtime["change_amount"], 2),
            "open": round_float(realtime["open"], 2),
            "prev_close": round_float(realtime["prev_close"], 2),
            "high": round_float(realtime["high"], 2),
            "low": round_float(realtime["low"], 2),
            "volume_hands": round_float(realtime["volume_hands"], 2),
            "volume_shares": round_float(realtime["volume_shares"], 2),
            "volume_wan_hands": round_float(realtime["volume_hands"] / 10000, 2),
            "amount_wan_yuan": round_float(realtime["amount_wan_yuan"], 2),
            "amount_yi_yuan": round_float(realtime["amount_yi_yuan"], 2),
            "turnover_rate": turnover_analysis.get("latest_turnover_rate"),
            "timestamp": realtime["timestamp"],
        },
        "kline_pattern": kline_pattern,
        "volume_price": volume_price,
        "volume_profile": volume_profile,
        "turnover_analysis": turnover_analysis,
        "chip_distribution": chip_distribution,
        "fund_flow": fund_flow,
        "moving_averages": moving_averages,
        "indicators": indicators,
        "score": {
            "total": total_score,
            "signal": score_signal,
            "components": {
                "trend": round_float(trend_score, 2),
                "momentum": round_float(momentum_score, 2),
                "volume_price": round_float(volume_score, 2),
                "pattern": round_float(pattern_score, 2),
            },
        },
        "support_resistance": support_resistance,
        "advice": advice,
    }


def generate_report(analysis_result: Dict, detailed: bool = False) -> str:
    """
    根据结构化分析结果渲染文本报告。
    """
    meta = analysis_result["meta"]
    realtime = analysis_result["realtime"]
    kline_pattern = analysis_result["kline_pattern"]["single"]
    engulfing = analysis_result["kline_pattern"]["engulfing"]
    volume_price = analysis_result["volume_price"]
    volume_profile = analysis_result["volume_profile"]
    turnover_analysis = analysis_result["turnover_analysis"]
    chip_distribution = analysis_result["chip_distribution"]
    fund_flow = analysis_result["fund_flow"]
    moving_averages = analysis_result["moving_averages"]
    indicators = analysis_result["indicators"]
    score = analysis_result["score"]
    support_resistance = analysis_result["support_resistance"]
    advice = analysis_result["advice"]

    lines = []
    title_icon = get_icon("title")
    title_prefix = f"{title_icon} " if title_icon else ""

    lines.append("=" * LINE_WIDTH)
    lines.append(f"{title_prefix}{meta['name']} ({meta['code']}) 形态分析报告")
    lines.append("=" * LINE_WIDTH)
    lines.append("")

    lines.append("【实时行情】")
    lines.append(f"最新价：{realtime['price']:.2f} 元  涨跌幅：{realtime['change_percent']:+.2f}%")
    lines.append(f"开盘：{realtime['open']:.2f} 元  昨收：{realtime['prev_close']:.2f} 元")
    lines.append(f"最高：{realtime['high']:.2f} 元  最低：{realtime['low']:.2f} 元")
    lines.append(
        f"成交量：{realtime['volume_wan_hands']:.1f} 万手  成交额：{realtime['amount_yi_yuan']:.2f} 亿"
    )
    if realtime["timestamp"]:
        lines.append(f"更新时间：{realtime['timestamp']}")
    lines.append("")

    lines.append("【K 线形态】")
    lines.append(f"形态：{kline_pattern['type']}")
    lines.append(
        f"实体：{kline_pattern['body']:+.2f} 元  上影线：{kline_pattern['upper_shadow']:.2f} 元  "
        f"下影线：{kline_pattern['lower_shadow']:.2f} 元"
    )
    lines.append(f"信号：{kline_pattern['signal']}")
    if engulfing["type"] != "无":
        lines.append(f"组合形态：{engulfing['type']}  解读：{engulfing['signal']}")
    lines.append("")

    lines.append("【量价关系】")
    icon = get_icon(volume_price["icon"])
    ratio_text = (
        f"{volume_price['volume_ratio']:.2f}" if volume_price["volume_ratio"] is not None else "不可用"
    )
    lines.append(f"量比：{ratio_text}  量价：{volume_price['relation']} {icon}")
    lines.append(f"解读：{volume_price['description']}")
    lines.append("")

    lines.append("【近期量能】")
    if volume_profile["available"]:
        lines.append(
            f"最新成交量：{volume_profile['latest_volume_wan_hands']:.2f} 万手  "
            f"近5日均量：{volume_profile['average_volume_wan_hands_5']:.2f} 万手  "
            f"近20日均量：{volume_profile['average_volume_wan_hands_20']:.2f} 万手"
        )
        lines.append(
            f"量能状态：{volume_profile['volume_state']}  5日量比：{volume_profile['volume_ratio_5']:.2f}  "
            f"20日量比：{volume_profile['volume_ratio_20']:.2f}"
        )
        lines.append(f"解读：{volume_profile['description']}")
    else:
        lines.append("近期量能：不可用")
        lines.append(f"解读：{volume_profile['description']}")
    lines.append("")

    lines.append("【换手率】")
    if turnover_analysis["available"]:
        lines.append(
            f"最新换手率：{turnover_analysis['latest_turnover_rate']:.2f}%  "
            f"近5日均值：{turnover_analysis['average_turnover_rate_5']:.2f}%  "
            f"近20日均值：{turnover_analysis['average_turnover_rate_20']:.2f}%"
        )
        lines.append(
            f"活跃度：{turnover_analysis['activity_level']}  "
            f"5日比值：{turnover_analysis['turnover_ratio_5']:.2f}  "
            f"20日比值：{turnover_analysis['turnover_ratio_20']:.2f}"
        )
        lines.append(f"解读：{turnover_analysis['description']}")
    else:
        lines.append("换手率：不可用")
        lines.append(f"解读：{turnover_analysis['description']}")
    lines.append("")

    lines.append("【筹码分布】")
    if chip_distribution["available"]:
        cost_range_90 = chip_distribution["cost_range_90"]
        lines.append(
            f"平均成本：{chip_distribution['average_cost']:.2f} 元  "
            f"获利盘：{chip_distribution['profit_ratio']:.2f}%  "
            f"现价相对成本：{chip_distribution['distance_to_average_cost_percent']:+.2f}%"
        )
        lines.append(
            f"90%成本区：{cost_range_90['low']:.2f} - {cost_range_90['high']:.2f} 元  "
            f"集中度：{cost_range_90['concentration']:.2f}%"
        )
        lines.append(f"位置：{chip_distribution['price_position']}")
        lines.append(f"解读：{chip_distribution['description']}")
    else:
        lines.append("筹码分布：不可用")
        lines.append(f"解读：{chip_distribution['description']}")
    lines.append("")

    lines.append("【资金流向】")
    if fund_flow["available"]:
        lines.append(
            f"主力净流入：{fund_flow['main_net_inflow_yi_yuan']:+.2f} 亿元  "
            f"净占比：{fund_flow['main_net_inflow_ratio']:+.2f}%"
        )
        lines.append(
            f"近3日累计：{fund_flow['cumulative_main_net_inflow_3d_yi_yuan']:+.2f} 亿元  "
            f"近5日累计：{fund_flow['cumulative_main_net_inflow_5d_yi_yuan']:+.2f} 亿元"
        )
        lines.append(
            f"超大单：{fund_flow['super_large_net_inflow_yi_yuan']:+.2f} 亿元  "
            f"大单：{fund_flow['large_net_inflow_yi_yuan']:+.2f} 亿元"
        )
        lines.append(f"解读：{fund_flow['description']}")
    else:
        lines.append("主力资金：不可用")
        lines.append(f"解读：{fund_flow['description']}")
    lines.append("")

    lines.append("【均线系统】")
    for label in ("ma5", "ma10", "ma20", "ma60"):
        data = moving_averages[label]
        label_text = label.upper()
        if data["value"] is None:
            lines.append(f"{label_text}: 不可用")
        else:
            lines.append(
                f"{label_text}: {data['value']:.2f} 元  股价位置：{data['distance_percent']:+.2f}%"
            )
    arrangement = moving_averages["arrangement"]
    arrangement_icon = get_icon("bullish") if arrangement["name"] == "多头排列" else (
        get_icon("bearish") if arrangement["name"] == "空头排列" else get_icon("neutral")
    )
    lines.append(f"排列：{arrangement['name']} {arrangement_icon}")
    lines.append("")

    if detailed:
        lines.append("【技术指标】")
        macd = indicators["macd"]
        if macd["dif"] is None:
            lines.append("MACD: 不可用")
        else:
            macd_icon = get_icon("bullish") if macd["signal"] in {"金叉", "多头上行"} else get_icon("bearish")
            lines.append(
                f"MACD: {macd['signal']} {macd_icon} (DIF:{macd['dif']:.2f}, DEA:{macd['dea']:.2f})"
            )
        rsi = indicators["rsi"]
        if rsi["value"] is None:
            lines.append("RSI(14): 不可用")
        else:
            lines.append(f"RSI(14): {rsi['value']:.1f}  {rsi['signal']}")
        bollinger = indicators["bollinger"]
        if bollinger["upper"] is None:
            lines.append("布林带：不可用")
        else:
            lines.append(
                f"布林带：上轨 {bollinger['upper']:.2f} 元  中轨 {bollinger['middle']:.2f} 元  "
                f"下轨 {bollinger['lower']:.2f} 元"
            )
            lines.append(f"位置：{bollinger['position']}  带宽：{bollinger['bandwidth']:.2f}%")
        lines.append("")

    lines.append("【技术评分】")
    score_icon = (
        get_icon("bullish") if score["total"] > 0.5 else
        get_icon("bearish") if score["total"] < -0.5 else
        get_icon("neutral")
    )
    lines.append(f"总分：{score['total']:+.2f}/5 {score_icon}")
    lines.append(
        "趋势：{trend:+.2f}  动能：{momentum:+.2f}  量价：{volume_price:+.2f}  形态：{pattern:+.2f}".format(
            **score["components"]
        )
    )
    lines.append(f"结论：{score['signal']}")
    lines.append("")

    lines.append("【支撑压力】")
    if support_resistance["resistance"]:
        resistance_text = " -> ".join(
            f"{item['price']:.2f} 元 ({item['source']})" for item in support_resistance["resistance"]
        )
        lines.append(f"压力位：{resistance_text}")
    else:
        lines.append("压力位：不可用")
    if support_resistance["support"]:
        support_text = " -> ".join(
            f"{item['price']:.2f} 元 ({item['source']})" for item in support_resistance["support"]
        )
        lines.append(f"支撑位：{support_text}")
    else:
        lines.append("支撑位：不可用")
    lines.append("")

    lines.append("【操作建议】")
    lines.append(f"建议：{advice['action']}")
    if advice["stop_loss"] is not None:
        lines.append(f"止损：{advice['stop_loss']:.2f} 元")
    if advice["target"] is not None:
        lines.append(f"目标：{advice['target']:.2f} 元")
    lines.append(f"说明：{advice['rationale']}")
    lines.append("")

    if analysis_result["warnings"]:
        lines.append("【数据提示】")
        warning_icon = get_icon("warning")
        for warning in analysis_result["warnings"]:
            lines.append(f"{warning_icon} {warning}")
        lines.append("")

    lines.append("=" * LINE_WIDTH)
    lines.append("以上分析仅供参考，不构成投资建议。")
    lines.append("股市有风险，投资需谨慎。")
    lines.append("=" * LINE_WIDTH)
    return "\n".join(lines)


def export_watchlist_csv(batch_result: Dict, output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([title for _, title in WATCHLIST_CSV_COLUMNS])
        for item in batch_result["summary"]:
            writer.writerow([item.get(field, "") for field, _ in WATCHLIST_CSV_COLUMNS])


def generate_watchlist_report(batch_result: Dict, detailed: bool = False) -> str:
    meta = batch_result["meta"]
    summary = batch_result["summary"]
    failures = batch_result["failures"]

    lines = []
    lines.append("=" * LINE_WIDTH)
    lines.append("自选股批量分析汇总")
    lines.append("=" * LINE_WIDTH)
    if meta.get("source"):
        lines.append(f"来源文件：{meta['source']}")
    lines.append(
        f"股票数量：{meta['requested']}  成功：{meta['completed']}  失败：{meta['failed']}"
    )
    lines.append(
        f"排序方式：按{WATCHLIST_SORT_LABELS[meta['sort_by']]}{'降序' if meta['sort_order'] == 'desc' else '升序'}"
    )
    lines.append("")

    lines.append("【汇总排名】")
    if summary:
        lines.append("排名 | 代码 | 名称 | 最新价 | 涨跌幅 | 评分 | 结论 | 建议")
        for item in summary:
            lines.append(
                f"{item['rank']:>2} | {item['code']} | {item['name']} | "
                f"{item['price']:.2f} | {item['change_percent']:+.2f}% | "
                f"{item['score']:+.2f} | {item['signal']} | {item['action']}"
            )
    else:
        lines.append("暂无成功的分析结果。")
    lines.append("")

    if failures:
        lines.append("【失败列表】")
        for failure in failures:
            lines.append(f"{failure['code']}: {failure['error']}")
        lines.append("")

    if detailed and batch_result["results"]:
        lines.append("【个股详情】")
        lines.append("")
        for index, analysis_result in enumerate(batch_result["results"]):
            if index:
                lines.append("")
            lines.append(generate_report(analysis_result, detailed=True))
        return "\n".join(lines)

    lines.append("=" * LINE_WIDTH)
    lines.append("以上分析仅供参考，不构成投资建议。")
    lines.append("股市有风险，投资需谨慎。")
    lines.append("=" * LINE_WIDTH)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A 股形态学分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/morph_analyzer.py --code 600867
  python3 scripts/morph_analyzer.py --code 000001 --detailed
  python3 scripts/morph_analyzer.py --code 600519 --json
  python3 scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
  python3 scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change --csv watchlist.csv
        """,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--code", help="股票代码")
    input_group.add_argument("--watchlist", help="自选股文件路径")
    parser.add_argument("--days", type=int, default=30, help="分析天数")
    parser.add_argument("--detailed", action="store_true", help="详细报告")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument(
        "--sort-by",
        choices=tuple(WATCHLIST_SORT_LABELS),
        default="score",
        help="批量模式排序字段",
    )
    parser.add_argument(
        "--sort-order",
        choices=("desc", "asc"),
        default="desc",
        help="批量模式排序方向",
    )
    parser.add_argument("--csv", help="批量模式导出的 CSV 路径")
    args = parser.parse_args()

    if args.csv and not args.watchlist:
        print("--csv 仅支持与 --watchlist 一起使用", file=sys.stderr)
        raise SystemExit(1)

    try:
        if args.watchlist:
            codes = load_watchlist_codes(args.watchlist)
            analysis_result = build_watchlist_analysis_result(
                codes,
                days=args.days,
                sort_by=args.sort_by,
                descending=args.sort_order == "desc",
                source=args.watchlist,
            )
            if args.csv:
                export_watchlist_csv(analysis_result, args.csv)
        else:
            analysis_result = build_analysis_result(args.code, days=args.days)
    except RuntimeError as exc:
        print(f"获取数据失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(analysis_result, indent=2, ensure_ascii=False))
        return

    if args.watchlist:
        print(generate_watchlist_report(analysis_result, detailed=args.detailed))
        return

    print(generate_report(analysis_result, detailed=args.detailed))


if __name__ == "__main__":
    main()
