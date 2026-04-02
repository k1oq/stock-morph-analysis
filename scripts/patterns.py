#!/usr/bin/env python3
"""
K 线形态识别模块。
"""
from __future__ import annotations

from typing import Dict


def identify_single_pattern(open_p: float, close_p: float, high_p: float, low_p: float) -> Dict:
    """
    识别单根 K 线形态。
    """
    body = float(close_p - open_p)
    upper_shadow = max(0.0, float(high_p - max(open_p, close_p)))
    lower_shadow = max(0.0, float(min(open_p, close_p) - low_p))
    total_range = float(high_p - low_p)

    result = {
        "type": "未知",
        "body": body,
        "upper_shadow": upper_shadow,
        "lower_shadow": lower_shadow,
        "signal": "",
        "bias": "neutral",
    }

    if total_range <= 0:
        result["type"] = "一字线"
        result["signal"] = "极端行情"
        return result

    body_ratio = abs(body) / total_range
    if body > 0:
        line_type = "阳线"
        bias = "bullish"
    elif body < 0:
        line_type = "阴线"
        bias = "bearish"
    else:
        line_type = "十字星"
        bias = "neutral"

    result["bias"] = bias

    if body_ratio <= 0.1:
        result["type"] = "十字星"
        result["signal"] = "多空平衡，可能变盘"
        result["bias"] = "neutral"
    elif body_ratio >= 0.7:
        result["type"] = f"大{line_type}"
        result["signal"] = "多头强势" if body > 0 else "空头强势"
    else:
        result["type"] = f"中{line_type}"
        result["signal"] = "多头占优" if body > 0 else "空头占优"

    # 用影线比例修正极端形态的结论。
    if lower_shadow > abs(body) * 2 and upper_shadow <= abs(body):
        result["type"] = "锤子线"
        result["signal"] = "下探回升，关注底部反转"
        result["bias"] = "bullish"
    elif upper_shadow > abs(body) * 2 and lower_shadow <= abs(body):
        result["type"] = "倒锤子"
        result["signal"] = "冲高回落，关注顶部反转"
        result["bias"] = "bearish"

    return result


def identify_engulfing_pattern(today: Dict, yesterday: Dict) -> Dict:
    """
    识别吞没形态。
    """
    today_body = float(today["close"] - today["open"])
    yesterday_body = float(yesterday["close"] - yesterday["open"])

    if today_body > 0 and yesterday_body < 0:
        if today["open"] <= yesterday["close"] and today["close"] >= yesterday["open"]:
            return {
                "type": "看涨吞没",
                "signal": "强烈看涨",
                "reliability": "高",
                "score": 0.5,
                "bias": "bullish",
            }

    if today_body < 0 and yesterday_body > 0:
        if today["open"] >= yesterday["close"] and today["close"] <= yesterday["open"]:
            return {
                "type": "看跌吞没",
                "signal": "强烈看跌",
                "reliability": "高",
                "score": -0.5,
                "bias": "bearish",
            }

    return {
        "type": "无",
        "signal": "",
        "reliability": "低",
        "score": 0.0,
        "bias": "neutral",
    }


def identify_doji_pattern(open_p: float, close_p: float, high_p: float, low_p: float) -> bool:
    """
    识别十字星。
    """
    total_range = float(high_p - low_p)
    if total_range <= 0:
        return False
    body = abs(float(close_p - open_p))
    return body / total_range <= 0.1
