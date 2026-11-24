# 支付宝银行积存金：半自动研究原型

本模块仅生成手动交易建议，**不会连接支付宝、不会下单，也不会保证止损成交**。

## 参数
- 初始本金 20,000 元；本金亏损上限 25%。
- 15% 预警降低目标仓位上限至 25%；20% 防御阈值目标清仓；25% 强制退出建议。
- 单资产、只做多、默认最大目标仓位 80%，交易最小名义额 100 元。
- 兴业、浙商、民生、广发的报价必须从支付宝实际买入/卖出页面人工核实；历史报道费率不可当作实时报价。

## 使用

```python
from datetime import datetime, timezone
from autotrader.gold import BankQuote, GoldAdvisor, Portfolio

now = datetime.now(timezone.utc)
quotes = [BankQuote("兴业", now, buy=900, sell=896)]  # 示例数据，非实时价格
signal = GoldAdvisor().advise(Portfolio(cash=20000, grams=0), quotes, target_weight=0.5, now=now)
print(signal)
```

运行测试：`python -m unittest discover -s tests -v`

## 关键边界
- 净值采用当前持仓银行的**卖出净收入**估值，避免按买入价高估资产。
- 当前持仓报价缺失或过期时禁止生成交易建议。
- 不自动跨银行转仓；换行需分别建模卖出与买入。
- 实际交易需要人工确认报价、营业时间、最低克数、金额、费用及订单是否成交。
- 25% 为本金亏损预算，不是最大回撤约束；实际价格跳空和人工延迟可能突破。
- 尚未接入真实行情源、交易日历、交易回执、预测模型、回测及通知通道；这些是后续工作。
