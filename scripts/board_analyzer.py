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
from io import StringIO
import json
import re
import statistics
import sys
import time
from typing import Dict, List, Optional

import pandas as pd
import requests


LINE_WIDTH = 66
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://q.10jqka.com.cn/",
}
BOARD_TYPE_NAMES = {
    "industry": "行业板块",
    "concept": "概念板块",
}
SUMMARY_PAGE_URLS = {
    "industry": "http://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/{page}/",
    "concept": "http://q.10jqka.com.cn/gn/index/field/addtime/order/desc/page/{page}/",
}
DETAIL_PAGE_URLS = {
    "industry": "http://q.10jqka.com.cn/thshy/detail/code/{code}/",
    "concept": "http://q.10jqka.com.cn/gn/detail/code/{code}/",
}
DETAIL_PAGE_PAGED_URLS = {
    "industry": "http://q.10jqka.com.cn/thshy/detail/code/{code}/page/{page}/",
    "concept": "http://q.10jqka.com.cn/gn/detail/code/{code}/page/{page}/",
}
DETAIL_LINK_PATTERNS = {
    "industry": re.compile(r'href="http://q\.10jqka\.com\.cn/thshy/detail/code/(\d+)/"[^>]*>([^<]+)</a>'),
    "concept": re.compile(r'href="http://q\.10jqka\.com\.cn/gn/detail/code/(\d+)/"[^>]*>([^<]+)</a>'),
}


def round_float(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, "", "--"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _request_text(
    url: str,
    retries: int = 4,
    raise_on_error: bool = False,
) -> Optional[str]:
    last_error = "未知错误"

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS)
            response.raise_for_status()
            response.encoding = "gbk"
            payload = response.text
            if not payload:
                raise RuntimeError("同花顺接口返回空响应")
            return payload
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))

    if raise_on_error:
        raise RuntimeError(last_error)
    return None


def _extract_total_pages(html: str) -> int:
    match = re.search(r'class="page_info">(\d+)/(\d+)</span>', html)
    if not match:
        return 1
    return max(int(match.group(2)), 1)


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(value))
    return re.sub(r"\s+", " ", text).replace("&nbsp;", " ").strip()


def _parse_percent(value: object) -> Optional[float]:
    if value in (None, "", "--"):
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_unit_value(value: object, default_unit: str = "") -> Optional[float]:
    if value in (None, "", "--"):
        return None

    text = str(value).strip().replace(",", "")
    text = text.replace("元", "").replace("股", "")
    multiplier = 1.0

    if text.endswith("亿"):
        multiplier = 100000000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    elif default_unit == "亿":
        multiplier = 100000000.0
    elif default_unit == "万":
        multiplier = 10000.0

    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _read_first_table(html: str) -> pd.DataFrame:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise RuntimeError("同花顺页面未返回表格数据") from exc
    if not tables:
        raise RuntimeError("同花顺页面未返回表格数据")
    dataframe = tables[0].copy()
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    return dataframe


def _extract_board_codes(html: str, board_type: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for code, name in DETAIL_LINK_PATTERNS[board_type].findall(html):
        clean_name = _clean_html_text(name)
        if clean_name and clean_name not in mapping:
            mapping[clean_name] = code
    return mapping


def normalize_text(value: str) -> str:
    return "".join(str(value).strip().lower().split())


def _fetch_board_list_by_type(board_type: str) -> List[Dict]:
    first_html = _request_text(SUMMARY_PAGE_URLS[board_type].format(page=1), raise_on_error=True)
    total_pages = _extract_total_pages(first_html)
    boards: List[Dict] = []

    for page in range(1, total_pages + 1):
        html = first_html if page == 1 else _request_text(
            SUMMARY_PAGE_URLS[board_type].format(page=page),
            raise_on_error=True,
        )
        if not html:
            continue

        try:
            dataframe = _read_first_table(html)
        except RuntimeError:
            continue
        code_map = _extract_board_codes(html, board_type)

        if board_type == "industry":
            for row in dataframe.to_dict(orient="records"):
                name = str(row.get("板块", "")).strip()
                code = code_map.get(name)
                if not name or not code:
                    continue
                boards.append(
                    {
                        "code": code,
                        "name": name,
                        "latest": None,
                        "change_percent": round_float(_parse_percent(row.get("涨跌幅"))),
                        "change_amount": None,
                        "market_cap": None,
                        "up_count": int(_safe_float(row.get("上涨家数"))),
                        "down_count": int(_safe_float(row.get("下跌家数"))),
                        "leader_name": str(row.get("领涨股", "")).strip() or None,
                        "leader_change_percent": round_float(_parse_percent(row.get("领涨股涨跌幅"))),
                        "board_type": board_type,
                        "board_type_name": BOARD_TYPE_NAMES[board_type],
                    }
                )
        else:
            for row in dataframe.to_dict(orient="records"):
                name = str(row.get("概念名称", "")).strip()
                code = code_map.get(name)
                if not name or not code:
                    continue
                boards.append(
                    {
                        "code": code,
                        "name": name,
                        "latest": None,
                        "change_percent": None,
                        "change_amount": None,
                        "market_cap": None,
                        "up_count": None,
                        "down_count": None,
                        "leader_name": str(row.get("龙头股", "")).strip() or None,
                        "leader_change_percent": None,
                        "constituent_count_hint": int(_safe_float(row.get("成分股数量"))),
                        "board_type": board_type,
                        "board_type_name": BOARD_TYPE_NAMES[board_type],
                    }
                )

    if not boards:
        raise RuntimeError(f"未获取到可用的{BOARD_TYPE_NAMES[board_type]}")
    return boards


def fetch_board_list(board_type: Optional[str] = None) -> List[Dict]:
    if board_type:
        return _fetch_board_list_by_type(board_type)

    boards: List[Dict] = []
    boards.extend(_fetch_board_list_by_type("industry"))
    boards.extend(_fetch_board_list_by_type("concept"))
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
                -(abs(item.get("change_percent") or 0)),
            )
        )
        return contains_matches[0]

    suggestions = build_board_suggestions(query, boards)
    suggestion_text = "、".join(suggestions) if suggestions else "无"
    raise RuntimeError(f"未找到板块：{query}。可尝试：{suggestion_text}")


def _fetch_board_snapshot(board_code: str, board_type: str) -> Dict:
    html = _request_text(DETAIL_PAGE_URLS[board_type].format(code=board_code), raise_on_error=True)
    pairs = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html, flags=re.S)
    info = { _clean_html_text(key): _clean_html_text(value) for key, value in pairs }

    prev_close = _parse_unit_value(info.get("昨收"))
    change_percent = _parse_percent(info.get("板块涨幅"))
    latest = None
    if prev_close is not None and change_percent is not None:
        latest = prev_close * (1 + change_percent / 100)

    up_count = None
    down_count = None
    rise_fall_text = info.get("涨跌家数", "")
    number_parts = re.findall(r"\d+", rise_fall_text)
    if len(number_parts) >= 2:
        up_count = int(number_parts[0])
        down_count = int(number_parts[1])

    return {
        "latest": round_float(latest),
        "change_percent": round_float(change_percent),
        "open": round_float(_parse_unit_value(info.get("今开"))),
        "prev_close": round_float(prev_close),
        "high": round_float(_parse_unit_value(info.get("最高"))),
        "low": round_float(_parse_unit_value(info.get("最低"))),
        "up_count": up_count,
        "down_count": down_count,
        "amount": round_float(_parse_unit_value(info.get("成交额(亿)"), default_unit="亿"), 0),
        "volume_hands": round_float(_parse_unit_value(info.get("成交量(万手)"), default_unit="万"), 0),
        "net_inflow": round_float(_parse_unit_value(info.get("资金净流入(亿)"), default_unit="亿"), 0),
    }


def fetch_board_constituents(board_code: str, board_type: str = "industry") -> List[Dict]:
    first_html = _request_text(DETAIL_PAGE_URLS[board_type].format(code=board_code), raise_on_error=True)
    total_pages = _extract_total_pages(first_html)
    constituents: List[Dict] = []
    seen_codes = set()

    for page in range(1, total_pages + 1):
        html = first_html if page == 1 else _request_text(
            DETAIL_PAGE_PAGED_URLS[board_type].format(code=board_code, page=page),
            raise_on_error=True,
        )
        if not html:
            continue

        try:
            dataframe = _read_first_table(html)
        except RuntimeError:
            continue
        for row in dataframe.to_dict(orient="records"):
            code = str(row.get("代码", "")).strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)

            amount = _parse_unit_value(row.get("成交额"))
            float_market_cap = _parse_unit_value(row.get("流通市值"))
            constituents.append(
                {
                    "code": code,
                    "name": str(row.get("名称", "")).strip(),
                    "price": round_float(_parse_unit_value(row.get("现价"))),
                    "change_percent": round_float(_parse_percent(row.get("涨跌幅(%)"))),
                    "change_amount": round_float(_parse_unit_value(row.get("涨跌"))),
                    "volume_hands": None,
                    "amount": round_float(amount, 0),
                    "turnover_rate": round_float(_parse_percent(row.get("换手(%)"))),
                    "volume_ratio": round_float(_parse_unit_value(row.get("量比"))),
                    "market_cap": round_float(float_market_cap, 0),
                    "float_market_cap": round_float(float_market_cap, 0),
                    "pe_ratio": round_float(_parse_unit_value(row.get("市盈率"))),
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
    industry_boards = fetch_board_list("industry")
    try:
        board = dict(match_board(query, industry_boards))
    except RuntimeError:
        concept_boards = fetch_board_list("concept")
        board = dict(match_board(query, concept_boards))

    if board.get("latest") is None or board.get("change_percent") is None:
        try:
            board.update(_fetch_board_snapshot(board["code"], board["board_type"]))
        except RuntimeError:
            pass

    constituents = fetch_board_constituents(board["code"], board_type=board["board_type"])

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
            "data_source": "ths",
        },
        "board": board,
        "summary": {
            "constituent_count": len(constituents),
            "official_change_percent": board.get("change_percent"),
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
    if board.get("latest") is not None and board.get("change_percent") is not None:
        lines.append(f"板块涨跌幅：{board['change_percent']:+.2f}%  板块点位：{board['latest']:.2f}")
    elif board.get("change_percent") is not None:
        lines.append(f"板块涨跌幅：{board['change_percent']:+.2f}%")
    else:
        lines.append("板块涨跌幅：不可用")
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
        result = build_board_analysis_result(args.industry, top_n=args.top)
    except RuntimeError as exc:
        print(f"板块数据获取失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(generate_board_report(result, top_n=args.top))


if __name__ == "__main__":
    main()
