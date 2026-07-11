# 聚宽小资金约束策略搜索结果

本轮目标不是寻找理论权重收益最高的策略，而是按照个人小资金账户在聚宽上的实际约束重新筛选：

- A 股 100 股一手；
- 资金量有限；
- 不能产生大量几百元目标市值订单；
- 避免不足一手、碎股、残余仓位导致聚宽报错；
- 用聚宽 `read_file(path)` 读取权重 CSV；
- 用 `order_target(security, amount)` 按目标股数下单。

## 搜索设置

数据：

- `data/market/csmar/stock/1d_combined_total_return`

候选权重：

- `reports/csmar_combined_fast_monthly_search/weights_*.csv`

本金假设：

- 5 万
- 10 万
- 20 万

执行约束搜索：

- `MAX_POSITIONS`: 5 / 8 / 10 / 15 / 20
- `MIN_POSITION_VALUE`: 2000 / 3000 / 5000 / 8000
- `CASH_BUFFER`: 2% / 5% / 10%
- `LOT_SIZE`: 100

搜索脚本：

- `scripts/search_joinquant_small_account.py`

结果目录：

- `reports/joinquant_small_account_search`

## 关键发现

原先全样本最优的 50 股组合，在小资金约束下会明显退化：

- 很多小权重股票买不起一手；
- 直接按目标市值下单会产生大量几百元目标订单；
- 聚宽会报“平仓数量必须是 100 的整数倍”“应当一次性平仓”等错误；
- 因此必须把策略执行层改成“先筛股票，再换算成一手整数股数”。

## 当前推荐小资金策略

推荐策略：

- 基础权重：`def_top50_liq0.60_capq0.75_cap`
- 聚宽执行参数：
  - `MAX_POSITIONS = 5`
  - `MIN_POSITION_VALUE = 8000.0`
  - `CASH_BUFFER = 0.10`
  - `LOT_SIZE = 100`

导出文件：

- `exports/joinquant/small_account_best_helper.py`
- `exports/joinquant/small_account_best_weights.csv`
- `exports/joinquant/small_account_best_summary.csv`

## 真实回测确认结果

| 本金 | 策略变体 | 年化收益 | Sharpe | 最大回撤 | 总收益 | 交易次数 |
|---:|---|---:|---:|---:|---:|---:|
| 200,000 | `def_top50_liq0.60_capq0.75_cap_cash200000_top5_min8000_buf0.10` | 8.82% | 0.63 | -34.65% | 239.21% | 764 |
| 100,000 | `def_top50_liq0.60_capq0.75_cap_cash100000_top20_min8000_buf0.10` | 7.51% | 0.54 | -34.18% | 184.54% | 459 |
| 50,000 | `def_top50_liq0.60_capq0.40_cap_cash50000_top20_min8000_buf0.10` | 7.48% | 0.53 | -43.22% | 183.64% | 96 |

## 结论

如果资金量约 20 万，当前最好版本是：

```python
MAX_POSITIONS = 5
MIN_POSITION_VALUE = 8000.0
CASH_BUFFER = 0.10
LOT_SIZE = 100
```

如果资金只有 5 万左右，这类股票组合会非常受限，真实效果明显变差，主要问题是：

- 可买股票太少；
- 高价股占用资金过大；
- 分散度不足；
- 回撤仍然偏大。

下一步如果目标资金低于 10 万，建议重新开发“低价高流动性 + 少股票 + 更强现金过滤”的专门小账户策略，而不是直接压缩当前大盘低波策略。

## 验证

- `python -m unittest discover -s tests -v`：40 tests passed
- `python -m compileall -q autotrader scripts tests`：passed
