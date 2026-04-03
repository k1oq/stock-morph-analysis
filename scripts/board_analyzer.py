#!/usr/bin/env python3
"""
A 股板块/行业分析工具。

使用方法:
    python3 scripts/board_analyzer.py --industry 半导体
    python3 scripts/board_analyzer.py --industry 半导体 --json
"""
from __future__ import annotations

import argparse
from datetime import datetime
from difflib import SequenceMatcher
import json
import statistics
import sys
import time
from typing import Dict, List, Optional

import requests


LINE_WIDTH = 66
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/center/boardlist.html",
}
BOARD_LIST_URLS = (
    "https://44.push2.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://17.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
)
BOARD_CONSTITUENT_URLS = (
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://44.push2.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
)
BOARD_TYPE_FILTERS = {
    "industry": ("m:90+t:2", "行业板块"),
    "concept": ("m:90+t:3", "概念板块"),
}


def round_float(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _request_json(
    url: str,
    params: Dict[str, str],
    retries: int = 5,
    timeout: int = 12,
    raise_on_error: bool = False,
) -> Optional[Dict]:
    last_error = "未知错误"

    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if payload is None:
                raise RuntimeError("板块接口返回空数据")
            return payload
        except (requests.exceptions.RequestException, ValueError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                time.sleep(1.2 * (attempt + 1))

    if raise_on_error:
        raise RuntimeError(last_error)
    return None


def _request_json_from_candidates(
    urls: tuple[str, ...],
    params: Dict[str, str],
    retries: int = 5,
    timeout: int = 12,
    raise_on_error: bool = False,
) -> Optional[Dict]:
    last_error = "未知错误"
    for url in urls:
        try:
            payload = _request_json(
                url=url,
                params=params,
                retries=retries,
                timeout=timeout,
                raise_on_error=True,
            )
            if payload is not None:
                return payload
        except RuntimeError as exc:
            last_error = str(exc)

    if raise_on_error:
        raise RuntimeError(last_error)
    return None


def normalize_text(value: str) -> str:
    return "".join(str(value).strip().lower().split())


def fetch_board_list() -> List[Dict]:
    boards: List[Dict] = []

    for board_type, (fs_value, board_type_name) in BOARD_TYPE_FILTERS.items():
        payload = _request_json_from_candidates(
            BOARD_LIST_URLS,
            params={
                "pn": "1",
                "pz": "1000",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": fs_value,
                "fields": "f12,f14,f2,f3,f4,f20,f104,f105",
            },
            raise_on_error=True,
        )
        items = payload.get("data", {}).get("diff", []) if payload else []
        for item in items:
            boards.append(
                {
                    "code": str(item.get("f12", "")).strip(),
                    "name": str(item.get("f14", "")).strip(),
                    "latest": round_float(item.get("f2")),
                    "change_percent": round_float(item.get("f3")),
                    "change_amount": round_float(item.get("f4")),
                    "market_cap": round_float(item.get("f20"), 0),
                    "up_count": int(_safe_float(item.get("f104"))),
                    "down_count": int(_safe_float(item.get("f105"))),
                    "board_type": board_type,
                    "board_type_name": board_type_name,
                }
            )

    if not boards:
        raise RuntimeError("未获取到板块列表")
    return boards


def build_board_suggestions(query: str, boards: List[Dict], limit: int = 5) -> List[str]:
    normalized_query = normalize_text(query)
    ranked = sorted(
        boards,
        key=lambda item: SequenceMatcher(None, normalized_query, normalize_text(item["name"])).ratio(),
        reverse=True,
    )
    suggestions = []
    for item in ranked:
        if item["name"] not in suggestions:
            suggestions.append(item["name"])
        if len(suggestions) >= limit:
            break
    return suggestions


def match_board(query: str, boards: List[Dict]) -> Dict:
    normalized_query = normalize_text(query)

    exact_matches = [
        item for item in boards
        if normalized_query in {normalize_text(item["name"]), normalize_text(item["code"])}
    ]
    if exact_matches:
        return exact_matches[0]

    contains_matches = [
        item for item in boards
        if normalized_query in normalize_text(item["name"]) or normalize_text(item["name"]) in normalized_query
    ]
    if contains_matches:
        contains_matches.sort(
            key=lambda item: (
                item["name"] != query,
                abs(len(item["name"]) - len(query)),
                -abs(item["change_percent"] or 0),
            )
        )
        return contains_matches[0]

    suggestions = build_board_suggestions(query, boards)
    suggestion_text = "、".join(suggestions) if suggestions else "无"
    raise RuntimeError(f"未找到板块：{query}。可尝试：{suggestion_text}")


def fetch_board_constituents(board_code: str) -> List[Dict]:
    payload = _request_json_from_candidates(
        BOARD_CONSTITUENT_URLS,
        params={
            "pn": "1",
            "pz": "5000",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": f"b:{board_code} f:!50",
            "fields": "f12,f14,f2,f3,f4,f5,f6,f8,f10,f20,f21",
        },
        raise_on_error=True,
    )
    items = payload.get("data", {}).get("diff", []) if payload else []
    constituents = []
    for item in items:
        constituents.append(
            {
                "code": str(item.get("f12", "")).strip(),
                "name": str(item.get("f14", "")).strip(),
                "price": round_float(item.get("f2")),
                "change_percent": round_float(item.get("f3")),
                "change_amount": round_float(item.get("f4")),
                "volume_hands": round_float(item.get("f5"), 0),
                "amount": round_float(item.get("f6"), 0),
                "turnover_rate": round_float(item.get("f8")),
                "volume_ratio": round_float(item.get("f10")),
                "market_cap": round_float(item.get("f20"), 0),
                "float_market_cap": round_float(item.get("f21"), 0),
            }
        )

    if not constituents:
        raise RuntimeError(f"板块 {board_code} 暂无成分股数据")
    return constituents


def identify_board_leaders(constituents: List[Dict], top_n: int = 5) -> List[Dict]:
    ranked = sorted(
        constituents,
        key=lambda item: (
            item["change_percent"] if item["change_percent"] is not None else -999,
            item["amount"] if item["amount"] is not None else 0,
            item["turnover_rate"] if item["turnover_rate"] is not None else 0,
            item["market_cap"] if item["market_cap"] is not None else 0,
        ),
        reverse=True,
    )
    return ranked[:top_n]


def build_board_analysis_result(query: str, top_n: int = 5) -> Dict:
    boards = fetch_board_list()
    board = match_board(query, boards)
    constituents = fetch_board_constituents(board["code"])

    changes = [item["change_percent"] for item in constituents if item["change_percent"] is not None]
    average_change = statistics.fmean(changes) if changes else 0.0
    median_change = statistics.median(changes) if changes else 0.0

    advancing = [item for item in constituents if (item["change_percent"] or 0) > 0]
    declining = [item for item in constituents if (item["change_percent"] or 0) < 0]
    flat = [item for item in constituents if item not in advancing and item not in declining]

    leaders = identify_board_leaders(constituents, top_n=top_n)
    top_gainers = sorted(
        constituents,
        key=lambda item: (
            item["change_percent"] if item["change_percent"] is not None else -999,
            item["amount"] if item["amount"] is not None else 0,
        ),
        reverse=True,
    )[:top_n]
    top_losers = sorted(
        constituents,
        key=lambda item: (
            item["change_percent"] if item["change_percent"] is not None else 999,
            -(item["amount"] if item["amount"] is not None else 0),
        )
    )[:top_n]

    return {
        "meta": {
            "query": query,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "board": board,
        "summary": {
            "constituent_count": len(constituents),
            "official_change_percent": board["change_percent"],
            "average_change_percent": round_float(average_change),
            "median_change_percent": round_float(median_change),
            "advancing_count": len(advancing),
            "declining_count": len(declining),
            "flat_count": len(flat),
        },
        "leaders": leaders,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "constituents": constituents,
    }


def generate_board_report(result: Dict, top_n: int = 5) -> str:
    board = result["board"]
    summary = result["summary"]
    leaders = result["leaders"][:top_n]
    top_gainers = result["top_gainers"][:top_n]
    top_losers = result["top_losers"][:top_n]

    lines = []
    lines.append("=" * LINE_WIDTH)
    lines.append(f"{board['name']} ({board['code']}) 板块分析")
    lines.append("=" * LINE_WIDTH)
    lines.append(f"匹配类型：{board['board_type_name']}")
    lines.append(
        f"板块涨跌幅：{board['change_percent']:+.2f}%  板块点位：{board['latest']:.2f}"
        if board["latest"] is not None and board["change_percent"] is not None
        else "板块涨跌幅：不可用"
    )
    lines.append(
        f"成分股数量：{summary['constituent_count']}  上涨：{summary['advancing_count']}  "
        f"下跌：{summary['declining_count']}  平盘：{summary['flat_count']}"
    )
    lines.append(
        f"成分股平均涨跌幅：{summary['average_change_percent']:+.2f}%  "
        f"中位数：{summary['median_change_percent']:+.2f}%"
    )
    lines.append("")

    lines.append("【龙头股】")
    for item in leaders:
        lines.append(
            f"{item['code']} {item['name']}  涨跌幅 {item['change_percent']:+.2f}%  "
            f"成交额 {item['amount']:.0f}"
        )
    lines.append("")

    lines.append("【涨幅居前】")
    for item in top_gainers:
        lines.append(f"{item['code']} {item['name']}  {item['change_percent']:+.2f}%")
    lines.append("")

    lines.append("【跌幅居前】")
    for item in top_losers:
        lines.append(f"{item['code']} {item['name']}  {item['change_percent']:+.2f}%")
    lines.append("")

    lines.append("=" * LINE_WIDTH)
    lines.append("以上分析仅供参考，不构成投资建议。")
    lines.append("=" * LINE_WIDTH)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A 股板块/行业分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/board_analyzer.py --industry 半导体
  python3 scripts/board_analyzer.py --industry 银行 --json
        """,
    )
    parser.add_argument("--industry", required=True, help="板块或行业名称")
    parser.add_argument("--top", type=int, default=5, help="文本报告展示条数")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    try:
        result = build_board_analysis_result(args.industry, top_n=max(args.top, 1))
    except RuntimeError as exc:
        print(f"获取数据失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(generate_board_report(result, top_n=max(args.top, 1)))


if __name__ == "__main__":
    main()
