# CSMAR 合并日频数据与策略重跑结果

本轮把三份 CSMAR「日个股回报率文件」合并为统一日频数据集，并在更长历史上重跑了基准、防守选股、CPU 月频 ML、市场状态过滤等候选。

## 1. 数据合并与落盘

原始目录：

- `data/日个股回报率文件2`：2011-07-11 至 2016-07-08
- `data/日个股回报率文件1`：2016-07-11 至 2021-07-09
- `data/日个股回报率文件`：2021-07-09 至 2026-07-08

合并后的标准行情：

- 路径：`data/market/csmar/stock/1d_combined`
- 覆盖：2011-07-11 至 2026-07-08
- 行数：13,343,779
- 股票数：5,793
- 交易日数：3,641
- 重复键：0
- 核心字段空值：0
- OHLC 异常：0

复权/总回报行情：

- 路径：`data/market/csmar/stock/1d_combined_total_return`
- 构造方式：使用 CSMAR `Dretwd` 逐证券构造总回报复权 close，再按复权比例调整 open/high/low
- 审计结果同样无重复键、核心空值和 OHLC 异常

月度特征：

- 路径：`data/features/csmar/monthly_price_volume_combined.parquet`
- 行数：663,424
- 股票数：5,790

2021 年两个下载包在边界日期有重叠，本轮导入器已按 `timestamp/symbol` 去重，2021 年去掉 4,436 条重复记录。

## 2. 基准策略

结果路径：`reports/csmar_combined_tr_benchmarks/full_period.csv`

| 策略 | 年化收益 | Sharpe | 最大回撤 |
|---|---:|---:|---:|
| top500_float_cap_weight | 3.81% | 0.41 | -27.28% |
| top1000_float_cap_weight | 3.13% | 0.40 | -21.86% |
| top1000_liquid_equal | 0.39% | 0.12 | -12.10% |
| top500_liquid_equal | -0.76% | -0.04 | -33.97% |

长样本下，朴素指数化/等权基准并不强；A 股 2011-2026 的大多数时间并不是简单 beta 友好的环境。

## 3. 当前最好的长样本候选：大盘、流动、低波、防回撤

结果路径：`reports/csmar_combined_fast_monthly_search/confirmed.csv`

最佳确认策略：

- `def_top50_liq0.40_capq0.75_cap`
- 年化收益：12.08%
- Sharpe：0.80
- 最大回撤：-33.09%
- 总收益：419.27%
- 交易次数：9,422
- 换手率：95.49
- 总交易成本：210,386

相近候选：

| 策略 | 年化收益 | Sharpe | 最大回撤 |
|---|---:|---:|---:|
| def_top50_liq0.40_capq0.75_cap | 12.08% | 0.80 | -33.09% |
| def_top50_liq0.40_capq0.60_cap | 11.81% | 0.78 | -32.75% |
| def_top50_liq0.40_capq0.40_cap | 11.80% | 0.78 | -32.72% |
| def_top50_liq0.60_capq0.75_cap | 11.95% | 0.78 | -35.06% |
| def_top50_liq0.60_capq0.40_cap | 11.68% | 0.77 | -34.18% |

和之前只看 2021-2026 的结果相比，年化收益类似，但长样本最大回撤明显变深，主要是把 2015、2018、2021-2024 等更复杂区间纳入后，策略真实左尾暴露出来了。

## 4. 滚动窗口结果

完整 3 个月步长滚动在 13M 行长样本上较慢，现阶段先输出了年度起点滚动窗口分布。

结果路径：`reports/csmar_combined_best_defensive_annual_rolling/rolling_summary.csv`

策略：`def_top50_liq0.40_capq0.75_cap`

| 窗口 | 窗口数 | 收益中位数 | 收益 5% 分位 | Sharpe 中位数 | 最大回撤中位数 | 盈利窗口占比 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 月 | 15 | 0.60% | -5.20% | 0.65 | -2.57% | 53.33% |
| 3 月 | 15 | 1.43% | -8.24% | 0.54 | -4.73% | 60.00% |
| 6 月 | 15 | 2.76% | -3.85% | 0.53 | -6.93% | 66.67% |
| 12 月 | 15 | 5.35% | -12.09% | 0.48 | -10.81% | 66.67% |
| 36 月 | 13 | 36.63% | 1.94% | 0.99 | -16.83% | 92.31% |

解读：

- 短窗口不稳定，1-3 个月亏损概率仍然不低。
- 36 个月窗口表现稳定得多，但这不是短线高夏普策略。
- 最大回撤仍然超过此前 15% 控制目标，需要额外风控或更好的资产/行业/指数对冲数据。

## 5. CPU 月频 ML 尝试

新增模块：

- `autotrader/strategies/monthly_ml.py`
- `scripts/run_csmar_monthly_ml.py`

测试覆盖：

- `tests/test_monthly_ml_strategy.py`

设计：

- 用月度价量/市值/波动排名特征预测下一月横截面收益排名
- 对每个预测月，只训练当时已经知道标签的历史样本，避免未来函数
- 先跑 Ridge 模型，避免 CPU 上直接做过重树模型搜索

结果路径：`reports/csmar_combined_monthly_ml/full_period.csv`

最佳 ML 候选：

- `ml_ridge_tw60_top100_cap`
- 年化收益：7.60%
- Sharpe：0.48
- 最大回撤：-58.56%

结论：当前纯价量月频 ML 没有打赢防守低波策略，且回撤显著更大。它能学到一点收益信号，但交易成本、风格暴露和左尾风险都偏高。

## 6. 市场状态过滤尝试

结果路径：`reports/csmar_combined_regime_overlay/confirmed.csv`

在最佳防守组合上增加「宽基动量/市场宽度」过滤：

- 强势时保留 85% 仓位
- 弱势时降至 0% 或 25%

最佳确认结果：

- 年化收益：9.90%
- Sharpe：0.76
- 最大回撤：-28.78%

结论：过滤能降低一点回撤和成本，但收益损失更大，Sharpe 没超过原始防守组合。暂不作为主策略。

## 7. 当前推荐基线

短期内建议把主 baseline 设为：

- 策略：`def_top50_liq0.40_capq0.75_cap`
- 权重文件：`reports/csmar_combined_fast_monthly_search/weights_def_top50_liq0.40_capq0.75_cap.csv`
- 数据：`data/market/csmar/stock/1d_combined_total_return`
- 特征：`data/features/csmar/monthly_price_volume_combined.parquet`

它不是高夏普策略，但在已有日频数据和现有成本假设下，是目前长样本确认结果最强的一条线。

## 8. 需要继续做的事

1. 优化 RollingWindowBacktester 性能。当前长样本密集滚动会重复切大表和重复跑引擎，13M 行下很慢。
2. 加入 ST、退市、涨跌停、停牌、上市不足期限等更严格可交易性过滤。
3. 下载/构造指数成分、行业、市值分层数据，用于做更真实的行业中性/市值中性评估。
4. 对防守低波策略增加组合约束：行业上限、单票上限、换手约束、动态止损。
5. ML 暂时保留为研究线；如果继续做，优先尝试 LightGBM/XGBoost 横截面 ranking，并严格做时间切分和 walk-forward。

## 9. 验证

- `python -m unittest discover -s tests -v`：38 tests passed
- `python -m compileall -q autotrader scripts tests`：passed
