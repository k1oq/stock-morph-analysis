# A 股形态学分析工具

基于腾讯财经实时行情和新浪财经历史 K 线的 A 股技术分析工具，支持 K 线形态、量价关系、均线系统、MACD、RSI、布林带、支撑压力位和结构化 JSON 报告。

## 功能特性

- 腾讯财经实时行情：获取最新价、涨跌幅、成交量、成交额
- 新浪历史 K 线：补齐均线、MACD、RSI、布林带、量比所需数据
- K 线形态识别：单 K 线形态 + 吞没形态
- 量价分析：基于近 5 个交易日平均成交量计算量比
- 均线系统：MA5 / MA10 / MA20 / MA60 与均线排列判断
- 技术评分：趋势、动能、量价、形态四个维度综合评分
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
```

## 输出结构

`--json` 会输出完整的分段嵌套结构，顶层包含：

- `meta`
- `data_status`
- `warnings`
- `realtime`
- `kline_pattern`
- `volume_price`
- `moving_averages`
- `indicators`
- `score`
- `support_resistance`
- `advice`

可参考 `templates/report_example.json`。

## 测试

```bash
# 单元测试
python -m unittest tests.test_indicators tests.test_analysis

# 联网 smoke test（验证 3 只股票）
python -m unittest tests.test_api
```

## 数据源说明

- 实时行情：`http://qt.gtimg.cn/q=sh600867`
- 历史 K 线：`http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600867&scale=240&datalen=120`

## 注意事项

- 成交量文本展示口径为“万手”，内部分析统一换算为“股”
- 成交额原始口径为“万元”，报告中换算为“亿元”
- 历史数据失败时，工具仍会输出实时分析，但依赖历史数据的字段会降级为不可用
- 结果仅供学习和研究，不构成投资建议
