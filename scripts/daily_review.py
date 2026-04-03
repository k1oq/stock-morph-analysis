#!/usr/bin/env python3
"""
A 股盘后复盘工具。

使用方法:
    python3 scripts/daily_review.py --date 2026-04-03
    python3 scripts/daily_review.py --date 2026-04-03 --json
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import sys
from typing import Dict, List

try:
    import akshare as ak
except ImportError:  # pragma: no cover
    ak = None

import numpy as np
import pandas as pd


LINE_WIDTH = 66


def normalize_trade_date(value: str) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    if len(digits) != 8:
        raise ValueError(f"无效日期格式：{value}")
    return digits


def display_trade_date(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def round_float(value: object, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(value), digits)


def to_builtin(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    return value


def dataframe_to_records(dataframe: pd.DataFrame) -> List[Dict]:
    records: List[Dict] = []
    for row in dataframe.to_dict(orient="records"):
        records.append({key: to_builtin(value) for key, value in row.items()})
    return records


def fetch_review_data(trade_date: str) -> Dict[str, pd.DataFrame]:
    if ak is None:
        raise RuntimeError("缺少 akshare 依赖，请先执行 pip install -r requirements.txt")

    try:
        limit_up = ak.stock_zt_pool_em(date=trade_date)
        limit_down = ak.stock_zt_pool_dtgc_em(date=trade_date)
        strong = ak.stock_zt_pool_strong_em(date=trade_date)
    except Exception as exc:  # pragma: no cover - 真实接口异常
        raise RuntimeError(f"复盘数据获取失败：{exc}") from exc

    if limit_up.empty and limit_down.empty and strong.empty:
        raise RuntimeError(f"{display_trade_date(trade_date)} 暂无可用复盘数据")

    return {
        "limit_up": limit_up,
        "limit_down": limit_down,
        "strong": strong,
    }


def build_market_sentiment(limit_up_count: int, limit_down_count: int, highest_streak: int) -> str:
    score = limit_up_count - limit_down_count + highest_streak * 2
    if score >= 20:
        return "情绪强势"
    if score >= 8:
        return "情绪偏暖"
    if score >= 0:
        return "情绪分化"
    return "情绪偏弱"


def select_board_leader(limit_up_rows: List[Dict], strong_rows: List[Dict]) -> str:
    candidates = []
    for row in limit_up_rows:
        candidates.append(
            (
                int(row.get("连板数") or 0),
                float(row.get("涨跌幅") or 0),
                float(row.get("成交额") or 0),
                f"{row.get('代码')} {row.get('名称')}",
            )
        )
    for row in strong_rows:
        candidates.append(
            (
                0,
                float(row.get("涨跌幅") or 0),
                float(row.get("成交额") or 0),
                f"{row.get('代码')} {row.get('名称')}",
            )
        )

    if not candidates:
        return ""
    return max(candidates)[-1]


def build_hot_boards(limit_up_df: pd.DataFrame, strong_df: pd.DataFrame, top_n: int = 10) -> List[Dict]:
    stats: Dict[str, Dict] = {}

    for row in dataframe_to_records(limit_up_df):
        industry = str(row.get("所属行业") or "").strip() or "未分类"
        entry = stats.setdefault(
            industry,
            {
                "board": industry,
                "limit_up_count": 0,
                "strong_count": 0,
                "highest_lianban": 0,
                "leader_stock": "",
                "_limit_up_rows": [],
                "_strong_rows": [],
            },
        )
        entry["limit_up_count"] += 1
        entry["highest_lianban"] = max(entry["highest_lianban"], int(row.get("连板数") or 0))
        entry["_limit_up_rows"].append(row)

    for row in dataframe_to_records(strong_df):
        industry = str(row.get("所属行业") or "").strip() or "未分类"
        entry = stats.setdefault(
            industry,
            {
                "board": industry,
                "limit_up_count": 0,
                "strong_count": 0,
                "highest_lianban": 0,
                "leader_stock": "",
                "_limit_up_rows": [],
                "_strong_rows": [],
            },
        )
        entry["strong_count"] += 1
        entry["_strong_rows"].append(row)

    hot_boards = []
    for item in stats.values():
        item["leader_stock"] = select_board_leader(item["_limit_up_rows"], item["_strong_rows"])
        item["hot_score"] = item["limit_up_count"] * 3 + item["strong_count"] + item["highest_lianban"]
        item.pop("_limit_up_rows")
        item.pop("_strong_rows")
        hot_boards.append(item)

    hot_boards.sort(
        key=lambda row: (
            row["hot_score"],
            row["limit_up_count"],
            row["highest_lianban"],
            row["strong_count"],
            row["board"],
        ),
        reverse=True,
    )
    return hot_boards[:top_n]


def build_daily_review_result(date: str) -> Dict:
    trade_date = normalize_trade_date(date)
    review_data = fetch_review_data(trade_date)

    limit_up_df = review_data["limit_up"]
    limit_down_df = review_data["limit_down"]
    strong_df = review_data["strong"]

    consecutive_limit_up_df = pd.DataFrame()
    if not limit_up_df.empty:
        consecutive_limit_up_df = limit_up_df[limit_up_df["连板数"] >= 2].copy()
        if not consecutive_limit_up_df.empty:
            consecutive_limit_up_df = consecutive_limit_up_df.sort_values(
                by=["连板数", "封板资金", "成交额"],
                ascending=[False, False, False],
            )

    highest_streak = int(consecutive_limit_up_df["连板数"].max()) if not consecutive_limit_up_df.empty else 0
    hot_boards = build_hot_boards(limit_up_df, strong_df)

    summary = {
        "limit_up_count": int(len(limit_up_df)),
        "limit_down_count": int(len(limit_down_df)),
        "strong_count": int(len(strong_df)),
        "consecutive_limit_up_count": int(len(consecutive_limit_up_df)),
        "highest_limit_up_streak": highest_streak,
        "sentiment": build_market_sentiment(len(limit_up_df), len(limit_down_df), highest_streak),
    }

    return {
        "meta": {
            "trade_date": display_trade_date(trade_date),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "summary": summary,
        "limit_up": dataframe_to_records(limit_up_df),
        "limit_down": dataframe_to_records(limit_down_df),
        "consecutive_limit_up": dataframe_to_records(consecutive_limit_up_df),
        "strong_pool": dataframe_to_records(strong_df),
        "hot_boards": hot_boards,
    }


def generate_daily_review_report(result: Dict, top_n: int = 10) -> str:
    summary = result["summary"]
    limit_up = result["limit_up"]
    limit_down = result["limit_down"]
    consecutive = result["consecutive_limit_up"][:top_n]
    hot_boards = result["hot_boards"][:top_n]

    lines = []
    lines.append("=" * LINE_WIDTH)
    lines.append(f"{result['meta']['trade_date']} 盘后复盘")
    lines.append("=" * LINE_WIDTH)
    lines.append(
        f"涨停家数：{summary['limit_up_count']}  跌停家数：{summary['limit_down_count']}  "
        f"强势股：{summary['strong_count']}"
    )
    lines.append(
        f"连板股：{summary['consecutive_limit_up_count']}  最高连板：{summary['highest_limit_up_streak']}  "
        f"情绪：{summary['sentiment']}"
    )
    lines.append("")

    lines.append("【涨停概览】")
    for item in limit_up[:top_n]:
        change_percent = round_float(item.get("涨跌幅")) or 0.0
        lines.append(
            f"{item['代码']} {item['名称']}  涨跌幅 {change_percent:+.2f}%  "
            f"连板 {int(item.get('连板数') or 0)}  行业 {item.get('所属行业')}"
        )
    if not limit_up:
        lines.append("暂无涨停股数据")
    lines.append("")

    lines.append("【跌停概览】")
    for item in limit_down[:top_n]:
        change_percent = round_float(item.get("涨跌幅")) or 0.0
        lines.append(
            f"{item['代码']} {item['名称']}  涨跌幅 {change_percent:+.2f}%  "
            f"连续跌停 {int(item.get('连续跌停') or 0)}  行业 {item.get('所属行业')}"
        )
    if not limit_down:
        lines.append("暂无跌停股数据")
    lines.append("")

    lines.append("【连板股】")
    for item in consecutive:
        seal_amount = round_float(item.get("封板资金"), 0) or 0.0
        lines.append(
            f"{item['代码']} {item['名称']}  {int(item.get('连板数') or 0)} 连板  "
            f"封板资金 {seal_amount:.0f}  行业 {item.get('所属行业')}"
        )
    if not consecutive:
        lines.append("暂无 2 连板及以上个股")
    lines.append("")

    lines.append("【热点板块】")
    for item in hot_boards:
        lines.append(
            f"{item['board']}  热度 {item['hot_score']}  涨停 {item['limit_up_count']}  "
            f"强势股 {item['strong_count']}  最高连板 {item['highest_lianban']}  龙头 {item['leader_stock']}"
        )
    if not hot_boards:
        lines.append("暂无可识别的热点板块")
    lines.append("")

    lines.append("=" * LINE_WIDTH)
    lines.append("以上复盘仅供参考，不构成投资建议。")
    lines.append("=" * LINE_WIDTH)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A 股盘后复盘工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/daily_review.py --date 2026-04-03
  python3 scripts/daily_review.py --date 20260403 --json
        """,
    )
    parser.add_argument("--date", required=True, help="交易日，支持 YYYY-MM-DD / YYYYMMDD")
    parser.add_argument("--top", type=int, default=10, help="文本报告展示条数")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    try:
        result = build_daily_review_result(args.date)
    except (RuntimeError, ValueError) as exc:
        print(f"获取数据失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(generate_daily_review_report(result, top_n=max(args.top, 1)))


if __name__ == "__main__":
    main()
