# CSMAR 全 A 日线导入与策略重跑结果

日期：2026-07-09

## 1. 已完成工作

新增 CSMAR 离线导入与审计脚本：

- `autotrader/data/sources/csmar.py`
- `scripts/import_csmar_daily.py`
- `scripts/audit_csmar_import.py`
- `scripts/run_csmar_benchmarks.py`
- `scripts/run_csmar_strategies.py`

新增测试：

- `tests/test_csmar_import.py`

## 2. 导入结果

源数据：

- `data/日个股回报率文件`
- `data/公司文件`
- `data/指数基本信息文件`

导入输出：

- `data/market/csmar/stock/1d/year=2021/bars.parquet`
- `data/market/csmar/stock/1d/year=2022/bars.parquet`
- `data/market/csmar/stock/1d/year=2023/bars.parquet`
- `data/market/csmar/stock/1d/year=2024/bars.parquet`
- `data/market/csmar/stock/1d/year=2025/bars.parquet`
- `data/market/csmar/stock/1d/year=2026/bars.parquet`

导入时过滤：

- `Markettype in {1, 4, 16, 32, 64}`
- `Curtrd == "CNY"`

即保留上证 A 股、深证 A 股、创业板、科创板、北证 A 股，排除 B 股。

质量检查：

| 指标 | 数值 |
|---|---:|
| A股日线行数 | 6,248,445 |
| A股代码数 | 5,725 |
| 交易日数 | 1,210 |
| 日期范围 | 2021-07-09 至 2026-07-08 |
| 重复 `(timestamp, symbol)` | 0 |
| 核心字段缺失 | 0 |
| OHLC 异常 | 0 |
| 每日 A股覆盖中位数 | 5,328.5 |

## 3. 基准策略

先跑动态股票池基准，避免继续拿静态 Top40 做比较。

| 策略 | 年化收益 | Sharpe | 最大回撤 | 说明 |
|---|---:|---:|---:|---|
| top1000_float_cap_weight | 1.71% | 0.333 | -9.53% | 流通市值前1000，市值权重 |
| top500_float_cap_weight | 1.54% | 0.259 | -11.49% | 流通市值前500，市值权重 |
| top1000_liquid_equal | -2.18% | -0.446 | -17.23% | 流动性前1000，等权 |
| top500_liquid_equal | -3.46% | -0.371 | -30.26% | 流动性前500，等权 |

解释：

2021-07 到 2026-07 这段 A 股环境偏弱。大盘市值权重基准小幅正收益、低回撤；等权/偏小盘基准明显更差。

这和之前 Top40 静态样本差异很大，说明之前结果确实包含较强样本选择/幸存者偏差。

## 4. 全 A 多因子策略

| 策略 | 年化收益 | Sharpe | 最大回撤 | 12M收益中位数 | 12M盈利窗口占比 |
|---|---:|---:|---:|---:|---:|
| csmar_defensive_top50_v08_liq60 | 0.06% | 0.071 | -20.15% | 1.05% | 60.00% |
| csmar_balanced_top30_v10_liq70 | -3.91% | -0.136 | -36.84% | -1.58% | 20.00% |
| csmar_balanced_top50_v10_liq70 | -4.74% | -0.202 | -38.06% | -3.17% | 20.00% |
| csmar_momentum_top30_v12_liq70 | -18.13% | -0.698 | -71.37% | -24.59% | 20.00% |

结论：

- 防守低波动组合基本打平，但没有明显超额收益。
- 动量组合在这段样本里表现很差。
- 之前在当前 Top40 样本中表现较好的多因子/动量逻辑，放到全 A 后失效明显。

## 5. 全 A Ridge ML 策略

| 策略 | 年化收益 | Sharpe | 最大回撤 | 12M收益中位数 | 12M盈利窗口占比 |
|---|---:|---:|---:|---:|---:|
| csmar_ridge_h5_top30_weekly | -13.47% | -0.816 | -55.01% | -18.07% | 20.00% |

结论：

Ridge ML 在全 A 样本上显著亏损。这个结果比之前 Top40 样本上的 ML 结果更可信，也更冷静：当前特征集不足以稳定预测全 A 未来 5 日收益。

## 6. 关键判断

这次重跑改变了项目的认识基础：

1. 当前 Top40 静态样本的高收益/高 Sharpe 不可靠。
2. 全 A 数据后，最稳的是大盘市值权重基准和低波防守，收益很低但回撤可控。
3. 动量在 2021-2026 这段 A 股样本里非常弱。
4. 简单技术特征 ML 在全 A 上没有正向 alpha。
5. 下一步不能继续靠调参数追高 Sharpe，应该先补复权、停牌、ST、涨跌停和历史指数成分股，然后重新定义可交易 universe。

## 7. 后续建议

优先级：

1. 补 CSMAR 指数成分股/权重。
2. 补复权因子或分红除权数据。
3. 补停牌/ST/涨跌停数据。
4. 对全 A 建立更干净的可交易股票池：
   - 剔除 ST；
   - 剔除上市不足 252 日；
   - 剔除低成交额；
   - 剔除北交所或单独处理；
   - 加涨跌停不可成交约束。
5. 重新做因子 IC 分析，而不是直接拼策略。
6. ML 方向先做预测诊断：
   - 分位数组合收益；
   - Rank IC；
   - 分年度表现；
   - 特征重要性；
   - 预测分数校准。

## 8. 输出文件

导入审计：

- `reports/csmar_import_audit/summary.csv`
- `reports/csmar_import_audit/yearly.csv`
- `reports/csmar_import_audit/daily_coverage.csv`

基准：

- `reports/csmar_benchmarks/full_period.csv`
- `reports/csmar_benchmarks/rolling_summary.csv`
- `reports/csmar_benchmarks/rolling_windows.csv`

策略：

- `reports/csmar_strategies_factor/full_period.csv`
- `reports/csmar_strategies_factor/rolling_summary.csv`
- `reports/csmar_strategies_factor/rolling_windows.csv`
- `reports/csmar_strategies_with_ml/full_period.csv`
- `reports/csmar_strategies_with_ml/rolling_summary.csv`
- `reports/csmar_strategies_with_ml/rolling_windows.csv`
