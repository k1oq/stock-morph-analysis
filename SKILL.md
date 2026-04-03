---
name: stock-morph-analysis
description: Analyze A-share stocks, watchlists, boards, and daily review flows in this repository. Use when Codex needs to run or extend `scripts/morph_analyzer.py`, `scripts/board_analyzer.py`, or `scripts/daily_review.py`; work with Tencent/Sina/THS/Eastmoney market data; export JSON or CSV; or validate market-analysis behavior end to end.
---

# Stock Morph Analysis

Use this skill when working in this repository so the existing CLI, tests, and data-source boundaries stay consistent.

## Scope

This repository currently focuses on text and JSON outputs.
Do not add `matplotlib`, candlestick charts, MACD/RSI subplots, or image export unless the user explicitly reopens charting as a new feature.

## Data Sources

- `scripts/tencent_api.py`: Tencent realtime quote data
- `scripts/sina_history.py`: Sina historical K-line data
- `scripts/market_extensions.py`: Tencent-based realtime turnover plus Eastmoney fund-flow data
- `scripts/board_analyzer.py`: THS / 同花顺 board and constituent data
- `scripts/daily_review.py`: daily market review flow, with AkShare-backed sources

Important boundary:

- Turnover analysis is currently based on Tencent realtime turnover only.
- Chip-distribution analysis has been removed. Do not reintroduce `chip_distribution` unless the user explicitly asks for a new implementation.

## Repo Map

- `scripts/morph_analyzer.py`: single-stock and watchlist entrypoint
- `scripts/board_analyzer.py`: board / industry analysis
- `scripts/daily_review.py`: daily market review
- `tests/test_analysis.py`: single-stock report tests
- `tests/test_market_extensions.py`: volume / turnover / fund-flow tests
- `tests/test_watchlist.py`: watchlist and CSV tests
- `tests/test_board_analysis.py`: board analysis tests
- `tests/test_daily_review.py`: daily review tests
- `templates/report_example.json`: current single-stock JSON example

## Mode Selection

Use single-stock mode for one stock:

```bash
python scripts/morph_analyzer.py --code 600867
python scripts/morph_analyzer.py --code 600867 --detailed
python scripts/morph_analyzer.py --code 600867 --json
```

Typical asks:

- “分析这只股票”
- “给我 600867 的 JSON”
- “看一下这只票最近量价和资金”
- “看下当前换手率”

Use watchlist mode for multiple stocks, ranking, or CSV:

```bash
python scripts/morph_analyzer.py --watchlist stocks.txt
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change
python scripts/morph_analyzer.py --watchlist stocks.txt --csv watchlist.csv
python scripts/morph_analyzer.py --watchlist stocks.txt --json
```

Typical asks:

- “分析我的自选股”
- “按评分排一下”
- “导出 CSV”

Use board mode for sectors, industries, breadth, leaders, or constituents:

```bash
python scripts/board_analyzer.py --industry 半导体
python scripts/board_analyzer.py --industry 银行 --json
```

Typical asks:

- “分析半导体板块”
- “看看银行板块龙头”
- “给我板块成分股和整体涨跌幅”

Use daily-review mode for a market recap by date:

```bash
python scripts/daily_review.py --date 2026-04-03
python scripts/daily_review.py --date 20260403 --json
```

Typical asks:

- “生成今日复盘”
- “看一下 2026-04-03 的涨停和热点板块”
- “识别今天的连板股”

## Skill Usage Recipes

### Single-Stock Analysis

When the user wants one stock report:

1. Run one of:

```bash
python scripts/morph_analyzer.py --code 600867 --detailed
python scripts/morph_analyzer.py --code 600867 --json
```

2. Prefer `--detailed` for human-readable output.
3. Prefer `--json` for downstream processing.
4. Summarize these sections when present:
   `volume_profile`, `turnover_analysis`, `fund_flow`, `score`, `advice`.
5. If external data partially fails, keep the result and surface `data_status` plus `warnings`.

### Watchlist Analysis

When the user wants batch analysis or ranking:

1. Ensure the watchlist file follows the repo format.
2. Run one of:

```bash
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change
python scripts/morph_analyzer.py --watchlist stocks.txt --csv watchlist.csv
python scripts/morph_analyzer.py --watchlist stocks.txt --json
```

3. Add `--csv` for spreadsheet-friendly output.
4. Add `--json` for machine-readable output.
5. Use `--sort-by score` or `--sort-by change` based on the user request.

### Board Analysis

When the user wants board or industry analysis:

1. Pass the user phrase directly to `--industry`.
2. Run one of:

```bash
python scripts/board_analyzer.py --industry 半导体
python scripts/board_analyzer.py --industry 半导体 --json
```

3. This workflow currently uses THS / 同花顺 pages, not Eastmoney board APIs.
4. Summarize:
   board change,
   constituent count,
   advancing / declining breadth,
   leader stocks,
   top gainers and losers when relevant.
5. If board-name matching fails, retry with the suggestions from the CLI error.

### Daily Review

When the user wants a post-market recap:

1. Normalize the exact trade date first.
2. Run one of:

```bash
python scripts/daily_review.py --date 2026-04-03
python scripts/daily_review.py --date 2026-04-03 --json
```

3. In the response, use the absolute date.
4. Summarize:
   limit-up count,
   limit-down count,
   consecutive limit-up stocks,
   strongest streak,
   hot boards.

## Output Notes

Single-stock JSON currently includes:

- `meta`
- `data_status`
- `warnings`
- `realtime`
- `kline_pattern`
- `volume_price`
- `volume_profile`
- `turnover_analysis`
- `fund_flow`
- `moving_averages`
- `indicators`
- `score`
- `support_resistance`
- `advice`

Do not claim `chip_distribution` exists in the current schema.

## Validation

Run focused tests after changes:

```bash
python -m unittest tests.test_analysis -v
python -m unittest tests.test_market_extensions -v
python -m unittest tests.test_watchlist -v
python -m unittest tests.test_board_analysis -v
python -m unittest tests.test_daily_review -v
```

Run the full suite before wrapping up larger changes:

```bash
python -m unittest tests.test_indicators tests.test_market_extensions tests.test_analysis tests.test_watchlist tests.test_board_analysis tests.test_daily_review -v
```

Recommended smoke tests:

```bash
python scripts/morph_analyzer.py --code 600867 --json
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score --json
python scripts/board_analyzer.py --industry 半导体 --json
python scripts/daily_review.py --date 2026-04-03 --json
```

## Guardrails

- Treat Tencent, Sina, THS, Eastmoney, and AkShare endpoints as flaky external dependencies.
- Preserve partial results whenever feasible instead of failing the whole workflow.
- Keep board parsing changes narrow and test-backed because THS page structure can change.
- Keep output language and field names stable unless the user asks for a breaking change.
- Do not present results as investment advice.
