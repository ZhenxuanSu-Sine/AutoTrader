# CPU 机器学习策略实验

本轮新增了一条 CPU 友好的机器学习策略管线，用于在现有回测框架中测试“滚动训练 → 逐期预测 → 选股 → 回测/滚动评测”的完整流程。

## 新增模块

- `autotrader/strategies/ml.py`
  - `ml_feature_frame`：生成滞后量价特征和未来收益标签。
  - `rolling_ml_prediction_weights`：滚动训练模型，并把预测分数转换为目标权重。
- `scripts/search_ml_candidates.py`
  - 默认运行 Ridge baseline。
  - 使用 `--include-slow-models` 时额外运行较慢的 HistGradientBoosting。
- `tests/test_ml_strategy.py`
  - 检查未来收益按 symbol 分组。
  - 检查 ML 权重 long-only、仓位上限和未来数据不影响已完成预测。

## 特征与训练方式

当前使用日线量价特征：

- 1/3/5/10/20/60 日收益；
- 5/20 日波动率；
- 20/60 日均线偏离；
- 60 日回撤；
- 日内振幅；
- 成交量/成交额相对 20 日均值。

标签是未来 5 日或 10 日收益。预测某日时，训练集只使用该日之前已经能观察到完整标签的样本，避免未来函数。信号仍由回测引擎在下一根 bar 开盘执行。

## 第一轮结果

数据范围：当前 CSI300 Top40 静态样本，日线。该样本仍有幸存者偏差，不能直接视为实盘可得收益。

### 固定全区间表现

| 策略 | 年化收益 | Sharpe | 最大回撤 | 有仓位信号占比 | 平均总仓位 |
|---|---:|---:|---:|---:|---:|
| ml_hgb_h5_top3_weekly | 32.18% | 1.180 | -34.27% | 99.82% | 79.60% |
| ml_ridge_h10_top3_weekly | 25.13% | 0.942 | -43.63% | 99.82% | 90.24% |
| ml_ridge_h10_top5_weekly | 25.41% | 0.881 | -38.89% | 99.82% | 112.67% |
| ml_ridge_h5_top3_weekly | 18.38% | 0.768 | -33.72% | 100.00% | 88.43% |

### 滚动窗口表现

| 策略 | 窗口 | 收益中位数 | 收益 5% 分位 | 收益 95% 分位 | Sharpe 中位数 | 最大回撤中位数 | 盈利窗口占比 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ml_hgb_h5_top3_weekly | 1M | 1.37% | -4.54% | 16.93% | 0.878 | -4.01% | 58.70% |
| ml_hgb_h5_top3_weekly | 3M | 2.78% | -7.73% | 28.52% | 0.575 | -10.42% | 67.39% |
| ml_hgb_h5_top3_weekly | 12M | 31.26% | -9.63% | 89.33% | 1.207 | -17.72% | 88.37% |
| ml_hgb_h5_top3_weekly | 36M | 138.31% | 51.75% | 230.17% | 1.285 | -20.11% | 100.00% |
| ml_ridge_h10_top3_weekly | 12M | 23.77% | -22.20% | 90.26% | 0.956 | -15.68% | 79.07% |
| ml_ridge_h5_top3_weekly | 12M | 18.39% | -18.49% | 56.92% | 0.931 | -17.39% | 74.42% |

## 解读

这轮最有价值的发现是：简单 ML 模型确实能在当前样本上改善规则策略表现，尤其是 `ml_hgb_h5_top3_weekly`。

但它不是“多数时间空仓”的策略，而是接近持续选股轮动：

- 有仓位信号占比接近 100%；
- 平均总仓位约 80%；
- 收益主要来自持续轮动，而不是只抓极少数行情。

风险点也很明显：

- 当前 universe 是“现时点 CSI300 Top40”，有明显幸存者偏差。
- 模型特征都来自日线，预测的是 5 日收益；这更像短周期 swing/轮动，不是真正分钟级高频。
- HGB 全区间 Sharpe 1.18 令人感兴趣，但仍需要真实历史成分股、更多股票、更严格样本外验证。
- 换手较高，`ml_hgb_h5_top3_weekly` 全区间交易成本约 284.7 万，成本模型对结果影响很大。

## 后续待办

1. 加真实历史成分股，消除当前 Top40 静态 universe 的幸存者偏差。
2. 加 Walk-forward 模型报告：每次训练的样本数、特征重要性、预测分布。
3. 引入更严格的 purged/embargo cross-validation。
4. 扩展到 XGBoost/LightGBM 参数搜索，但这会明显增加 CPU 时间。
5. 后续若接入分钟级数据，可把标签改成日内/隔日收益，并加入盘口/VWAP/成交额冲击特征。

## 输出文件

- `reports/ml_candidates/full_period_screen.csv`
- `reports/ml_candidates/ranking.csv`
- `reports/ml_candidates/rolling_windows.csv`
- `reports/ml_candidates/rolling_summary.csv`
- `reports/ml_candidates/hgb_probe.csv`
- `reports/ml_candidates/selected_rolling_windows.csv`
- `reports/ml_candidates/selected_rolling_summary.csv`
