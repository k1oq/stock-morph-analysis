# A 股形态学分析工具

基于腾讯财经实时行情、新浪财经历史 K 线和东方财富扩展市场数据的 A 股技术分析工具，支持 K 线形态、量价关系、近期量能、换手率、筹码分布、主力资金流、均线系统、MACD、RSI、布林带、支撑压力位和结构化 JSON 报告。

## 功能特性

- 腾讯财经实时行情：获取最新价、涨跌幅、成交量、成交额
- 新浪历史 K 线：补齐均线、MACD、RSI、布林带、量比所需数据
- K 线形态识别：单 K 线形态 + 吞没形态
- 量价分析：基于近 5 个交易日平均成交量计算量比
- 近期量能分析：补充近 5 / 20 日成交量对比，识别放量、缩量与量价配合
- 换手率分析：补充近 5 / 20 日换手率均值和活跃度判断
- 筹码分布分析：基于日线价格与换手率估算平均成本、获利盘和 70% / 90% 成本区
- 主力资金流向：跟踪主力净流入、超大单/大单行为和近 3 / 5 日累计资金方向
- 均线系统：MA5 / MA10 / MA20 / MA60 与均线排列判断
- 技术评分：趋势、动能、量价、形态四个维度综合评分
- 自选股批量分析：支持读取 `stocks.txt`、批量汇总、按评分/涨跌幅排序、导出 CSV
- 板块分析：支持查询板块成分股、板块涨跌幅、龙头股
- 盘后复盘：支持涨停/跌停数据、连板股和热点板块识别
- 双输出模式：文本报告和完整 JSON 结构
- 异常处理：历史 K 线失败时自动降级为实时分析，并给出 `warnings`

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
# 基础分析
python scripts/morph_analyzer.py --code 600867

# 详细报告（包含 MACD / RSI / 布林带）
python scripts/morph_analyzer.py --code 600867 --detailed

# JSON 输出
python scripts/morph_analyzer.py --code 600867 --json

# 指定分析天数（历史请求条数至少会补足到 120）
python scripts/morph_analyzer.py --code 600867 --days 60

# 批量分析自选股，并按评分排序
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by score

# 按涨跌幅排序并导出 CSV
python scripts/morph_analyzer.py --watchlist stocks.txt --sort-by change --csv watchlist.csv

# 分析板块/行业
python scripts/board_analyzer.py --industry 半导体

# 生成盘后复盘
python scripts/daily_review.py --date 2026-04-03
```

`stocks.txt` 支持一行一个代码，也支持空行、注释行和逗号/空格分隔：

```text
600867
600519
# 银行
000001
300750, 601318
```

## 输出结构

单股模式下，`--json` 会输出完整的分段嵌套结构，顶层包含：

- `meta`
- `data_status`
- `warnings`
- `realtime`
- `kline_pattern`
- `volume_price`
- `volume_profile`
- `turnover_analysis`
- `chip_distribution`
- `fund_flow`
- `moving_averages`
- `indicators`
- `score`
- `support_resistance`
- `advice`

可参考 `templates/report_example.json`。

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

## 测试

```bash
# 单元测试
python -m unittest tests.test_indicators tests.test_market_extensions tests.test_analysis tests.test_watchlist tests.test_board_analysis tests.test_daily_review

# 联网 smoke test（验证 3 只股票）
python -m unittest tests.test_api
```

## 数据源说明

- 实时行情：`http://qt.gtimg.cn/q=sh600867`
- 历史 K 线：`http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600867&scale=240&datalen=120`
- 东方财富日线扩展：`https://push2his.eastmoney.com/api/qt/stock/kline/get`
- 东方财富资金流：`https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`

## 注意事项

- 成交量文本展示口径为“万手”，内部分析统一换算为“股”
- 成交额原始口径为“万元”，报告中换算为“亿元”
- 历史数据失败时，工具仍会输出实时分析，但依赖历史数据的字段会降级为不可用
- 结果仅供学习和研究，不构成投资建议
