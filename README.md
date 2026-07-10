# AutoTrader

面向 A 股及可扩展多资产的量化研究框架。当前版本优先打通一个可信的最小闭环：

`标准行情 → 策略目标仓位 → A 股约束成交 → 净值/交易记录 → 因子评测`

项目采用渐进式重构：新的研究内核位于 `autotrader/`，早期 AKShare 下载脚本和
Backtrader 原型暂时保留，便于复用已有数据与对照结果。

## 当前能力

- 日线和分钟线共用的长表行情契约：`timestamp, symbol, open, high, low, close, volume`
- 中文/英文供应商字段归一化及严格 OHLCV 校验
- 多标的目标权重回测，信号在下一根 K 线开盘成交，避免最常见的未来函数
- A 股基础约束：100 股买入单位、T+1、佣金最低收费、卖出印花税、双向滑点
- 逐时点现金、持仓、成交和净值明细
- 收益、年化收益、波动率、夏普和最大回撤
- 动量、波动率基线因子，以及 Rank IC、ICIR、分位数组合收益
- 均线和买入持有基线策略

当前回测器定位为“研究与快速筛选”，并非实盘撮合器。涨跌停、停牌、退市、分红送转、
期货保证金等规则会在后续执行层逐项加入。

## 快速运行

要求 Python 3.10+。核心仅依赖 NumPy 和 Pandas。

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python -m examples.quickstart
```

数据下载和 Parquet 支持是可选依赖：

```powershell
python -m pip install -e ".[data]"
```

## 最小用法

```python
from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.strategies import moving_average_weights

# bars 是长表 DataFrame，同一 timestamp 可以包含多只证券
weights = moving_average_weights(bars, fast=5, slow=20, weight=0.8)
result = PortfolioEngine(BacktestConfig(initial_cash=1_000_000)).run(bars, weights)

print(result.metrics)
print(result.trades.tail())
print(result.equity.tail())
```

因子研究：

```python
from autotrader.factors import evaluate_factor, momentum

factor = momentum(bars, window=20)
report = evaluate_factor(factor, bars, periods=5, quantiles=5)
print(report.summary)
```

## 目录

```text
autotrader/
  core/          资产、频率、费用等领域模型
  data/          数据契约与校验
  strategies/    生成目标仓位的策略
  backtest/      组合成交模拟
  factors/       因子计算和横截面评测
  evaluation/    绩效指标
examples/        可离线运行的端到端示例
tests/           防未来函数、交易约束和数据质量测试
data/, scripts/  旧版数据源与下载工具（兼容保留）
```

详细边界和后续路线见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 真实数据 baseline

仓库包含一个小型、可复现的日线 baseline：下载 5 只长期上市 A 股的前复权行情，并运行
买入持有、均线择时、时间序列动量、等权组合、趋势组合和横截面动量。

```powershell
python -m scripts.download_baseline_data
python -m scripts.run_baselines
```

完整结果见 [BASELINE_RESULTS.md](BASELINE_RESULTS.md)。原始数据和逐策略成交/净值文件分别保存在
`data/market/akshare_sina/stock/1d/` 与 `reports/baseline/`，默认不提交到 Git。

## Rolling Window Backtest

滚动评测按自然月生成 1、3、6、12、36 个月窗口，默认每月向前滚动一步。每个窗口使用独立
现金和持仓，沿用 `PortfolioEngine` 的下一根 K 线成交、A 股费用和 T+1 逻辑，并在窗口末日
进行带费用和滑点的终端清仓。

```powershell
python -m scripts.run_rolling_baselines

# 日常快速迭代可每 3 个月取一个起点
python -m scripts.run_rolling_baselines --step-months 3
```

输出：

- `reports/rolling_baseline/windows.csv`：每个策略、每个窗口的完整指标
- `reports/rolling_baseline/summary.csv`：所有指标的均值、中位数、标准差及 5/25/75/95 分位数
- `reports/rolling_baseline/comparison.csv`：用于横向比较的精简列
- [ROLLING_BASELINE_RESULTS.md](ROLLING_BASELINE_RESULTS.md)：本次真实数据结果

Python API 位于 `autotrader.evaluation.rolling`。策略工厂可以读取窗口开始前的历史完成指标
warm-up，但必须保持因果性：时间 `t` 的权重只能依赖 `t` 及以前的数据。现有 baseline 仅使用
trailing rolling 和 `pct_change`，并由回归测试验证窗口结束后的未来数据不会改变已结束窗口。

## High-Sharpe 研究候选

`autotrader.strategies.high_sharpe` 提供多周期趋势、双动量轮动、防御复合、市场宽度过滤和信号
集成。所有实现均为长仓、不加杠杆、NumPy/Pandas CPU 计算。

```powershell
# 约 47 组参数的样本内搜索；先全区间筛选，再做12个月滚动筛选
python -m scripts.search_high_sharpe_candidates

# 对选出的不同策略族进行完整 1/3/6/12/36 月 rolling 评测
python -m scripts.run_high_sharpe_candidates
```

结果见 [HIGH_SHARPE_CANDIDATES.md](HIGH_SHARPE_CANDIDATES.md)。深度学习方向及其数据/GPU前置条件
记录在 [TODO.md](TODO.md)，当前日线小样本不启用深度模型。

## 动态选股

多因子选股将股票池资格、截面评分和组合配置拆开：个股需要至少252个交易日历史并通过流动性
和长期趋势过滤，再按20/60/120日动量、低波动和浅回撤打分，月度选择Top-N并进行逆波动配置。

```powershell
# 获取当前沪深300市值前40只的静态快照和前复权日线
python -m scripts.download_selection_universe

# 搜索均衡、动量、防御三类选股参数
python -m scripts.search_stock_selection

# 对选出的候选运行多窗口评测；默认每3个月取一个起点
python -m scripts.run_stock_selection_candidates
```

结果见 [STOCK_SELECTION_RESULTS.md](STOCK_SELECTION_RESULTS.md)。当前Token没有Tushare历史指数成分权限，
所以这个股票池存在幸存者偏差；正式研究必须替换成历史时点可见的成分股。

## 进攻型实验

进攻层支持显式1.5/2倍总敞口、负现金融资和逐日融资成本，并提供集中动量、突破和核心卫星
候选。普通回测默认仍限制为1倍，不会自动启用杠杆。

```powershell
python -m scripts.search_aggressive_candidates
python -m scripts.run_aggressive_candidates
```

结果见 [AGGRESSIVE_CANDIDATES.md](AGGRESSIVE_CANDIDATES.md)。当前40只静态大盘股样本中，能够满足
年化、Sharpe和回撤约束的候选仍无法达到2%-3%的月收益中位数。
