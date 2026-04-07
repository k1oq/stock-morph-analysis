# A 股形态分析工具

基于腾讯财经实时行情、新浪财经历史 K 线、同花顺板块页面和东方财富资金流数据的 A 股分析工具。
当前支持单股分析、自选股批量分析、板块分析和盘后复盘，输出文本报告或结构化 JSON。
另外支持股价阈值监控：到达指定价位后生成事件文件，并通过 `openclaw` 官方 webhook 回调。

## 功能

- 腾讯财经实时行情：最新价、涨跌幅、成交量、成交额、当前换手率
- 新浪历史 K 线：均线、MACD、RSI、布林带、量价关系所需历史数据
- K 线形态识别：单 K 线形态与吞没形态
- 量价分析：近期放量、缩量、量比与价格配合
- 换手率分析：基于腾讯财经实时换手率判断活跃度
- 主力资金流：东方财富近 1 / 3 / 5 日主力净流入、超大单、大单情况
- 自选股批量分析：支持 `--watchlist`、评分/涨跌幅排序、CSV 导出
- 板块分析：基于同花顺板块页面获取成分股、整体涨跌幅、龙头股
- 盘后复盘：涨停/跌停、连板股、热点板块识别
- 股价监控告警：达到目标价后写入事件 JSON 并调用 `openclaw` webhook
- 双输出模式：文本报告和 JSON

## 安装

```bash
pip install -r requirements.txt
```

## 用法

```bash
# 单股分析
python scripts/morph_analyzer.py --code 600867
python scripts/morph_analyzer.py --code 600867 --detailed
python scripts/morph_analyzer.py --code 600867 --json

# 自选股批量分析
python scripts/morph_analyzer.py --watchlist stocks.txt
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change --csv watchlist.csv

# 板块分析
python scripts/board_analyzer.py --industry 半导体
python scripts/board_analyzer.py --industry 半导体 --json

# 盘后复盘
python scripts/daily_review.py --date 2026-04-03
python scripts/daily_review.py --date 2026-04-03 --json

# 股价监控
python scripts/price_watcher.py --config watcher.json --once
python scripts/price_watcher.py --config watcher.json --interval 30
```

`stocks.txt` 支持：

- 每行一个代码
- 空行
- `#` 注释
- 逗号或空格分隔
- 自动去重

示例：

```text
600867
600519
# bank
000001
300750, 601318
```

`watcher.json` 示例见 [templates/watcher_example.json](/d:/下载/stock-morph-analysis/templates/watcher_example.json)。

监控配置字段：

- `openclaw`：`openclaw` webhook 配置
- `event_dir`：事件 JSON 输出目录，默认 `runtime/events`
- `watchers`：监控规则数组

`openclaw` 字段：

- `base_url`：`openclaw` Gateway 地址，例如 `http://127.0.0.1:18789`
- `token`：webhook token，放在 `x-openclaw-token` 请求头
- `endpoint`：`agent` 或 `wake`，默认 `agent`
- `wake_mode`：`now` 或 `next-heartbeat`，默认 `next-heartbeat`
- `name`：`agent` 模式下展示名称，默认 `Stock Watcher`
- `deliver`：是否由 `openclaw` 继续向用户通道投递
- `channel` / `to` / `model` / `thinking`：按需透传给 `openclaw /hooks/agent`

每条规则字段：

- `id`：规则唯一标识
- `code`：股票代码
- `target_price`：目标价
- `direction`：`gte` 或 `lte`
- `enabled`：是否启用，默认 `true`
- `cooldown_seconds`：重复触发冷却秒数，默认 `300`

## JSON 输出结构

单股模式下，`--json` 顶层包含：

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

批量模式下，`--json` 顶层包含：

- `meta`
- `codes`
- `summary`
- `results`
- `failures`

板块分析模式下，`--json` 顶层包含：

- `meta`
- `board`
- `summary`
- `leaders`
- `top_gainers`
- `top_losers`
- `constituents`

盘后复盘模式下，`--json` 顶层包含：

- `meta`
- `summary`
- `limit_up`
- `limit_down`
- `consecutive_limit_up`
- `strong_pool`
- `hot_boards`

完整示例见 [templates/report_example.json](/d:/下载/stock-morph-analysis/templates/report_example.json)。

## 测试

```bash
python -m unittest tests.test_indicators tests.test_market_extensions tests.test_analysis tests.test_watchlist tests.test_board_analysis tests.test_daily_review -v
python -m unittest tests.test_api -v
```

## 数据源

- 腾讯财经实时行情：`http://qt.gtimg.cn`
- 新浪财经历史 K 线：`http://money.finance.sina.com.cn`
- 同花顺板块与成分股：`http://q.10jqka.com.cn`
- 东方财富资金流：`https://push2his.eastmoney.com`
- AkShare 盘后复盘辅助数据

## 注意事项

- 当前版本已移除筹码分布分析，不再输出 `chip_distribution`
- 换手率分析目前基于腾讯财经实时换手率，不提供历史 5 / 20 日换手率均值
- 板块分析改为同花顺页面抓取，外部页面结构变化时可能需要同步调整解析逻辑
- 所有结果仅供学习和研究，不构成投资建议
