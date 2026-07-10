# CSMAR 新数据策略再开发结果

日期：2026-07-09

## 背景

上一次直接把旧策略搬到 CSMAR 全 A 日线后，指标很低。主要原因有两个：

1. 旧策略使用未复权 OHLC 做动量和波动率信号。
2. 2021-07 至 2026-07 这段 A 股环境中，简单动量和等权小盘暴露表现很差。

本轮先修正数据口径，再重新开发策略。

## 1. 构建总回报复权日线

新增脚本：

- `scripts/build_csmar_total_return_bars.py`

输入：

- `data/market/csmar/stock/1d`

输出：

- `data/market/csmar/stock/1d_total_return`

方法：

- 使用 CSMAR `return_with_dividend` 重建每只股票的总回报 close；
- 用 `adjusted_close / raw_close` 缩放 open/high/low/close；
- 保留 `raw_close` 和 `adjustment_factor`。

复权后，大盘市值基准明显改善：

| 策略 | 原始年化 | 原始 Sharpe | 复权年化 | 复权 Sharpe | 复权最大回撤 |
|---|---:|---:|---:|---:|---:|
| top1000_float_cap_weight | 1.71% | 0.33 | 3.22% | 0.62 | -7.63% |
| top500_float_cap_weight | 1.54% | 0.26 | 3.70% | 0.57 | -9.39% |

结论：后续策略开发应默认使用 `1d_total_return`。

## 2. 构建月度因子矩阵

新增脚本：

- `scripts/build_csmar_monthly_features.py`

输出：

- `data/features/csmar/monthly_price_volume.parquet`

行数：

- 314,487 月度截面行
- 5,722 个股票代码

预计算字段包括：

- 5/20/60/120 日收益；
- 20/60 日年化波动率；
- 120 日回撤；
- 20 日成交额均值；
- 流通市值；
- 上述字段的月度截面 rank。

这个步骤解决了全 A 搜索太慢的问题：滚动因子只算一次，后续策略搜索只处理月度截面。

## 3. 新策略：大盘低波防守组合

新增策略函数：

- `autotrader/strategies/defensive.py`
- `large_cap_low_vol_monthly_weights`

最佳候选：

```text
def_top50_liq0.40_capq0.40_cap
```

逻辑：

1. 每月第一个交易日调仓。
2. 要求上市/可观察历史不少于 252 个交易日。
3. 保留流动性 rank 前 60%。
4. 保留流通市值 rank 前 60%。
5. 综合打分：
   - 55% 低波动；
   - 25% 浅回撤；
   - 20% 大市值。
6. 选 Top50。
7. 按流通市值加权。

该策略本质上是“高流动性大盘低波组合”，不是动量策略。

## 4. 固定全区间结果

区间：

- 2021-07-09 至 2026-07-08

| 策略 | 年化收益 | Sharpe | 最大回撤 | Sortino | Calmar | 换手 | 总成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| def_top50_liq0.40_capq0.40_cap | 12.63% | 1.03 | -11.76% | 1.28 | 1.07 | 31.20 | 3.88万 |

对比：

| 策略 | 年化收益 | Sharpe | 最大回撤 |
|---|---:|---:|---:|
| top1000_float_cap_weight | 3.22% | 0.62 | -7.63% |
| top500_float_cap_weight | 3.70% | 0.57 | -9.39% |
| csmar_defensive_top50_v08_liq60 | 6.39% | 0.54 | -17.28% |
| def_top50_liq0.40_capq0.40_cap | 12.63% | 1.03 | -11.76% |

## 5. 滚动窗口结果

| 窗口 | 窗口数 | 收益中位数 | 收益 5% 分位 | 收益 95% 分位 | Sharpe 中位数 | 最大回撤中位数 | 盈利窗口占比 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 12M | 9 | 15.00% | -3.59% | 30.85% | 1.29 | -9.20% | 66.67% |
| 36M | 5 | 61.43% | 38.80% | 85.39% | 1.34 | -11.76% | 100.00% |

解读：

- 固定全区间 Sharpe 已超过 1。
- 最大回撤控制在 12% 左右，满足之前“15% 回撤”目标。
- 36 个月滚动窗口表现稳定。
- 12 个月窗口仍有亏损左尾，5% 分位约 -3.6%。

## 6. 重要限制

这个策略仍然不是最终实盘策略。

当前还缺：

1. ST 逐日状态；
2. 停牌逐日状态；
3. 涨跌停价格/状态；
4. 指数成分股/权重；
5. 更长历史区间。

现在用的是公司表里的当前/状态字段和日行情存在性，尚不能严格模拟涨停买不进、跌停卖不出、停牌不可交易等细节。

## 7. 当前建议

下一步不要再优先追 Sharpe 2，而是围绕这个新策略做稳健性增强：

1. 补 ST/停牌/涨跌停数据，做可交易过滤。
2. 做参数稳定性测试：
   - Top30/50/100；
   - 流动性阈值 40%/50%/60%；
   - 低波/回撤/市值权重扰动。
3. 做行业暴露分析，避免策略只是押注银行/公用事业。
4. 做年度归因和月度收益分布。
5. 加动态风险 overlay，把回撤接近 10% 时降仓。

## 8. 输出文件

数据：

- `data/market/csmar/stock/1d_total_return`
- `data/features/csmar/monthly_price_volume.parquet`

搜索：

- `reports/csmar_fast_monthly_search/approx_screen.csv`
- `reports/csmar_fast_monthly_search/confirmed.csv`
- `reports/csmar_fast_monthly_search/weights_def_top50_liq0.40_capq0.40_cap.csv`

滚动评测：

- `reports/csmar_selected_defensive_single/full_period.csv`
- `reports/csmar_selected_defensive_single/rolling_summary.csv`
- `reports/csmar_selected_defensive_single/rolling_windows.csv`
