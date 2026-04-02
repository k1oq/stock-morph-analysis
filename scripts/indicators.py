#!/usr/bin/env python3
"""
技术指标计算模块。
包含：MA / EMA / MACD / RSI / 布林带
"""
from __future__ import annotations

from typing import Dict, Sequence

import pandas as pd


def _to_series(prices: Sequence[float]) -> pd.Series:
    return pd.Series([float(price) for price in prices], dtype="float64")


def calc_ma(prices: Sequence[float], period: int) -> float:
    """
    计算移动平均线。
    当数据不足时，返回现有样本均值，避免抛异常。
    """
    if not prices:
        return 0.0

    series = _to_series(prices)
    if len(series) < period:
        return float(series.mean())
    return float(series.rolling(window=period).mean().iloc[-1])


def calc_ema(prices: Sequence[float], period: int) -> float:
    """
    计算指数移动平均线。
    """
    if not prices:
        return 0.0

    series = _to_series(prices)
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def calc_macd(prices: Sequence[float]) -> Dict:
    """
    计算 MACD 指标。
    """
    if len(prices) < 35:
        return {
            "dif": 0.0,
            "dea": 0.0,
            "macd": 0.0,
            "signal": "数据不足",
            "dif_prev": 0.0,
            "dea_prev": 0.0,
        }

    series = _to_series(prices)
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    histogram = (dif - dea) * 2

    dif_prev = float(dif.iloc[-2])
    dea_prev = float(dea.iloc[-2])
    dif_now = float(dif.iloc[-1])
    dea_now = float(dea.iloc[-1])

    if dif_prev <= dea_prev and dif_now > dea_now:
        signal = "金叉"
    elif dif_prev >= dea_prev and dif_now < dea_now:
        signal = "死叉"
    elif dif_now > dea_now:
        signal = "多头上行"
    else:
        signal = "空头下行"

    return {
        "dif": dif_now,
        "dea": dea_now,
        "macd": float(histogram.iloc[-1]),
        "signal": signal,
        "dif_prev": dif_prev,
        "dea_prev": dea_prev,
    }


def calc_rsi(prices: Sequence[float], period: int = 14) -> float:
    """
    计算 RSI 指标。
    """
    if len(prices) < period + 1:
        return 50.0

    series = _to_series(prices)
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = float(gains.rolling(window=period).mean().iloc[-1])
    avg_loss = float(losses.rolling(window=period).mean().iloc[-1])

    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0

    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def calc_bollinger(prices: Sequence[float], period: int = 20) -> Dict:
    """
    计算布林带。
    """
    if len(prices) < period:
        return {
            "upper": 0.0,
            "middle": 0.0,
            "lower": 0.0,
            "bandwidth": 0.0,
        }

    series = _to_series(prices)
    middle = float(series.rolling(window=period).mean().iloc[-1])
    std = float(series.rolling(window=period).std(ddof=0).iloc[-1])

    upper = middle + 2 * std
    lower = middle - 2 * std
    bandwidth = ((upper - lower) / middle * 100) if middle else 0.0

    return {
        "upper": float(upper),
        "middle": float(middle),
        "lower": float(lower),
        "bandwidth": float(bandwidth),
    }


def get_rsi_signal(rsi: float) -> str:
    """
    根据 RSI 值输出区间描述。
    """
    if rsi >= 80:
        return "超买区，警惕回调"
    if rsi >= 70:
        return "强势区，多头强势"
    if rsi >= 55:
        return "偏强区，多头占优"
    if rsi >= 45:
        return "中性区，等待方向"
    if rsi >= 30:
        return "偏弱区，空头占优"
    if rsi >= 20:
        return "弱势区，空头强势"
    return "超卖区，可能反弹"
