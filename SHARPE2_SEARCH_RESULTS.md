# Sharpe 2 策略搜索记录

目标：在当前 CPU 环境和现有 A 股日线样本上，尝试构造 Sharpe 达到 2 的策略。

结论：本轮没有找到可信的 Sharpe 2 候选。当前最强的可复现候选仍是 `ml_hgb_h5_top3_weekly`，固定全区间 Sharpe 约 1.18；做 15% 回撤控制后 Sharpe 约 1.19。为了追到 2，本轮尝试了多条路径，但都没有实质突破。

## 已尝试方案

### 1. HGB ML 选股基线

上一轮最强候选：

| 策略 | 年化收益 | Sharpe | 最大回撤 |
|---|---:|---:|---:|
| ml_hgb_h5_top3_weekly | 32.18% | 1.18 | -34.27% |
| ml_hgb_h5_top3_risk0.40 | 12.71% | 1.19 | -14.61% |

缩放仓位可以控制回撤，但不会显著提高 Sharpe。

### 2. 市场状态过滤

尝试了中期趋势、市场宽度、低波动过滤，例如：

- 60/120/200 日市场代理趋势；
- 20/60/120 日宽度；
- 20 日市场波动率上限；
- 牛市/低波动组合 gate。

结果：过滤后 Sharpe 下降，HGB 从 1.18 降到约 0.85–0.90。说明 HGB 的收益不是简单来自“只在牛市交易”，粗糙市场 gate 会砍掉太多有效交易。

### 3. 预测分数阈值

让 HGB 输出 `prediction`，然后只保留预测值较高的交易。

结果：阈值越严格，交易越少，但 Sharpe 下降。说明当前模型预测值的绝对大小没有很好校准；排序有用，但“置信度”不可靠。

### 4. HGB 参数变体

尝试：

- Top1 / Top3 / Top5；
- 5 日 / 10 日预测；
- 日频 / 周频调仓。

代表结果：

| 策略 | 年化收益 | Sharpe | 最大回撤 |
|---|---:|---:|---:|
| hgb_h5_top5_weekly | 31.45% | 1.07 | -41.88% |
| hgb_h5_top1_weekly | 21.28% | 1.02 | -28.39% |
| hgb_h5_top3_daily | 4.80% | 0.31 | -52.21% |

周频 Top3 仍是相对最优。

### 5. 单资产/简单规则搜索

对当前 Top40 静态股票池逐只测试：

- buy & hold；
- MA60 / MA120；
- 20+60 日动量；
- 60+120 日动量。

最高 Sharpe 约 1.20，达不到 2；且部分收益来自极强单票趋势，回撤很大。

### 6. 策略组合

组合组件包括：

- HGB ML；
- 多因子选股；
- 防守多因子；
- 突破策略；
- 若干低波动/大盘股票 buy & hold 代理。

策略收益流层面的理论搜索最高 Sharpe 约 1.54，正式权重混合回测更低。说明当前候选之间的相关性和交易成本结构不足以自然组合出 Sharpe 2。

### 7. 权益曲线择时

用 HGB 影子策略权益曲线做 gate：

- 权益曲线高于 MA；
- 影子策略回撤不超过阈值；
- gate 滞后一日，避免同日未来函数。

结果：最高 Sharpe 约 1.03，低于原始 HGB。

## 当前判断

在当前条件下，Sharpe 2 不是简单调参能达到的：

1. 当前样本是静态 Top40，信息量太少。
2. 日线特征对 5 日收益的预测能力有限。
3. A 股单边 long-only 策略在交易成本和回撤下很难稳定到 2。
4. 已有 ML 分数排序有效，但分数校准不好，难以通过“只做高置信度交易”提升 Sharpe。
5. 组合候选的相关性不够低，无法自然叠出 Sharpe 2。

## 暂时保留的最好版本

如果继续在当前框架内推进，我建议保留两个版本：

| 用途 | 策略 | 年化收益 | Sharpe | 最大回撤 |
|---|---|---:|---:|---:|
| 进攻版 | ml_hgb_h5_top3_weekly | 32.18% | 1.18 | -34.27% |
| 风控版 | ml_hgb_h5_top3_risk0.40 | 12.71% | 1.19 | -14.61% |

它们没有达到 Sharpe 2，但比其它尝试更稳。

## 深度学习方案备案

如果后续要认真冲击 Sharpe 2，我建议把深度学习放在“第二阶段研究”而不是现在直接上。原因是当前日线 Top40 数据量太小，深度学习很容易只是制造更华丽的过拟合。

备案方向：

1. 数据
   - 扩展到全 A 或至少历史 CSI300/CSI500 成分股；
   - 使用分钟级数据；
   - 增加成交额、VWAP、日内波动、开盘缺口、午后趋势、盘口代理特征。

2. 模型
   - Temporal Convolutional Network；
   - Transformer Encoder；
   - TabNet / FT-Transformer；
   - LightGBM/XGBoost 作为强 baseline，深度模型必须超过它们才有意义。

3. 训练方式
   - Walk-forward；
   - Purged / embargo cross-validation；
   - 按时间切分，禁止随机切分；
   - 输出预测校准报告，而不只看收益。

4. 策略层
   - 模型只负责 alpha；
   - 独立风险模型控制波动、回撤、行业暴露、单票集中度；
   - 组合层做动态风险预算。

5. 算力
   - CPU 可先跑 LightGBM/XGBoost；
   - Transformer/TCN 建议 GPU；
   - 暂不在当前纯 CPU 项目里强行加入深度学习训练依赖。

## 输出文件

- `reports/sharpe2_search/hgb_gate_probe.csv`
- `reports/sharpe2_search/hgb_prediction_threshold_screen.csv`
- `reports/sharpe2_search/hgb_model_variants.csv`
- `reports/sharpe2_search/single_asset_rules.csv`
- `reports/sharpe2_search/component_metrics.csv`
- `reports/sharpe2_search/strategy_level_allocation_search.csv`
- `reports/sharpe2_search/hgb_equity_curve_timing.csv`
