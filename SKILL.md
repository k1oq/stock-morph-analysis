---
name: stock-morph-analysis
description: Analyze A-share stocks, boards, and daily market review data with this repository's CLI and Python modules. Use when Codex needs to run or extend `scripts/morph_analyzer.py`, `scripts/board_analyzer.py`, or `scripts/daily_review.py`; inspect Tencent/Sina/Eastmoney market data integrations; generate text or JSON reports for a single stock, a watchlist, a board, or a trade date; identify board leaders, consecutive limit-up stocks, and hot sectors; export CSV; or validate market-analysis behavior in this codebase.
---

# Stock Morph Analysis

Use this skill to work efficiently in this repository without re-discovering the workflow.

## Goal

Produce or modify technical-analysis outputs for A-share stocks and market-wide review flows.
Support single-stock, watchlist, board, and daily-review workflows.
Prefer using the existing CLI and test suite instead of reimplementing behavior.

## Current Scope

This repository currently focuses on text and JSON outputs.
Do not add `matplotlib`, candlestick chart rendering, MACD/RSI subplot generation, or image export by default.
If a future user explicitly reopens charting work, treat that as a new feature request instead of assuming charts belong in the current baseline.

## Repo Map

- `scripts/morph_analyzer.py`: main CLI entrypoint and analysis orchestration
- `scripts/board_analyzer.py`: board and industry analysis
- `scripts/daily_review.py`: daily market review
- `scripts/tencent_api.py`: realtime quote fetcher
- `scripts/sina_history.py`: historical K-line fetcher
- `scripts/patterns.py`: candlestick pattern recognition
- `scripts/indicators.py`: MA, MACD, RSI, Bollinger helpers
- `tests/test_analysis.py`: single-stock analysis tests
- `tests/test_watchlist.py`: batch/watchlist tests
- `tests/test_board_analysis.py`: board analysis tests
- `tests/test_daily_review.py`: daily review tests
- `tests/test_api.py`: live network smoke tests
- `templates/report_example.json`: example JSON output shape

## Choose The Right Mode

Use single-stock mode when the user wants one report or one JSON payload.

```bash
python scripts/morph_analyzer.py --code 600867
python scripts/morph_analyzer.py --code 600867 --detailed
python scripts/morph_analyzer.py --code 600867 --json
```

Typical asks that map here:

- “分析这只股票”
- “给我 JSON 结果”
- “看一下 600867”

Use watchlist mode when the user provides multiple stock codes, a file such as `stocks.txt`, wants ranking, or wants CSV export.

```bash
python scripts/morph_analyzer.py --watchlist stocks.txt
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-order asc
python scripts/morph_analyzer.py --watchlist stocks.txt --csv watchlist.csv
python scripts/morph_analyzer.py --watchlist stocks.txt --json
```

Typical asks that map here:

- “分析我的自选股”
- “按评分排一下”
- “导出 CSV”

Use board mode when the user wants a sector or industry view, component stocks, board breadth, or leading names.

```bash
python scripts/board_analyzer.py --industry 半导体
python scripts/board_analyzer.py --industry 银行 --json
```

Typical asks that map here:

- “分析半导体板块”
- “看看银行板块龙头”
- “给我板块成分股和整体涨跌幅”

Use daily-review mode when the user wants a market recap for a trade date, including limit-up/down statistics, consecutive limit-up stocks, or hot sectors.

```bash
python scripts/daily_review.py --date 2026-04-03
python scripts/daily_review.py --date 20260403 --json
```

Typical asks that map here:

- “生成今日复盘”
- “看一下 2026-04-03 的涨停和热点板块”
- “识别今天的连板股”

## Watchlist Input Rules

Expect `--watchlist` files to support:

- one code per line
- blank lines
- `#` comments
- space-separated or comma-separated codes on one line
- duplicate codes that should be de-duplicated

Example:

```text
600867
600519
# bank
000001
300750, 601318
```

## Skill Usage Recipes

Use these recipes for the newly added workflows so another agent can act without guessing.

### Watchlist Analysis

When the user asks for batch analysis, ranking, or CSV export for multiple stocks:

1. Prepare or locate a watchlist file such as `stocks.txt`.
2. Run one of:

```bash
python scripts/morph_analyzer.py --watchlist stocks.txt
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change
python scripts/morph_analyzer.py --watchlist stocks.txt --csv watchlist.csv
python scripts/morph_analyzer.py --watchlist stocks.txt --json
```

3. If the user asks for spreadsheet output, add `--csv`.
4. If the user asks for machine-readable output or downstream processing, add `--json`.
5. If the user asks for “按评分” or “按涨跌幅”, set `--sort-by score` or `--sort-by change`.

### Board Analysis

When the user asks for industry/board analysis, board breadth, component stocks, or 龙头股:

1. Start with the user phrase directly as the `--industry` value.
2. Run one of:

```bash
python scripts/board_analyzer.py --industry 半导体
python scripts/board_analyzer.py --industry 银行
python scripts/board_analyzer.py --industry 半导体 --json
```

3. If the command reports a board-name mismatch, retry with the suggested board name from the error message.
4. In the response, summarize:
   board overall change,
   constituent count and breadth,
   leader stocks,
   top gainers/losers when relevant.
5. If the user asks for structured output, add `--json`.

### Daily Review

When the user asks for post-market recap, 涨停/跌停统计, 连板股, or 热点板块:

1. Normalize the date to the exact trade date the user requested.
2. Run one of:

```bash
python scripts/daily_review.py --date 2026-04-03
python scripts/daily_review.py --date 20260403
python scripts/daily_review.py --date 2026-04-03 --json
```

3. In the response, explicitly include the absolute date, not just “today”.
4. Summarize:
   limit-up count,
   limit-down count,
   consecutive limit-up stocks,
   highest streak,
   hot boards.
5. If the user wants structured or reusable output, add `--json`.

## Agent Workflow

1. Inspect whether the user wants single-stock analysis, watchlist ranking, board analysis, or a daily review.
2. Prefer updating the existing script that already owns the workflow instead of duplicating logic.
3. If output structure changes, update tests and any example JSON or README snippets that are now stale.
4. If the user wants machine-readable output, prefer `--json`.
5. If the user wants ranking across many stocks, prefer `--watchlist` plus `--sort-by`.
6. If the user wants spreadsheet-friendly output, use `--csv`.
7. If the user wants board breadth or leaders, use `scripts/board_analyzer.py`.
8. If the user wants limit-up/down review or hot sectors for a date, use `scripts/daily_review.py`.
9. If the user asks for verification, run the narrowest relevant tests first, then a CLI smoke test if useful.

## Validation

Run focused unit tests after code changes:

```bash
python -m unittest tests.test_analysis -v
python -m unittest tests.test_watchlist -v
python -m unittest tests.test_board_analysis -v
python -m unittest tests.test_daily_review -v
python -m unittest tests.test_indicators tests.test_analysis tests.test_watchlist tests.test_board_analysis tests.test_daily_review -v
```

Run a real CLI smoke test when the change touches arguments, rendering, sorting, or export behavior:

```bash
python scripts/morph_analyzer.py --help
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score --csv watchlist.csv
python scripts/board_analyzer.py --industry 半导体
python scripts/daily_review.py --date 2026-04-03
```

Run `tests/test_api.py` only when live network verification is worth the extra latency and external dependency risk.

## Guardrails

- Treat Tencent, Sina, Eastmoney, and AkShare-backed endpoints as flaky external dependencies; partial failures are possible.
- In batch mode, preserve successful results and surface per-code failures instead of failing the whole run when possible.
- In board and daily-review mode, prefer partial summaries and clear error messages when one data source is unavailable.
- Keep charting out of scope unless the user explicitly asks to bring it back in a future change.
- Keep output language and field names consistent with the existing CLI and JSON structure unless the user asks for a breaking change.
- Do not present the output as investment advice.

## Typical Change Hotspots

- Add or adjust CLI flags in `scripts/morph_analyzer.py`.
- Add or adjust CLI flags in `scripts/board_analyzer.py` and `scripts/daily_review.py`.
- Extend structured output in `build_analysis_result` or watchlist summary helpers.
- Update report rendering in `generate_report`, `generate_watchlist_report`, `generate_board_report`, or `generate_daily_review_report`.
- Add regression tests in `tests/test_analysis.py`, `tests/test_watchlist.py`, `tests/test_board_analysis.py`, or `tests/test_daily_review.py`.
