"""回测引擎模块。

提供Backtrader回测引擎的封装。
"""

from typing import Type
import backtrader as bt
from data.loaders.backtrader_loader import BacktraderDataLoader


class BacktestEngine:
    """回测引擎类。

    封装Backtrader的Cerebro，提供简洁的回测接口。
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        commission: float = 0.001,
        slippage: float = 0.0,
    ):
        """
        Args:
            initial_cash: 初始资金
            commission: 手续费率（交易金额的比例）
            slippage: 滑点率（价格的比例）
        """
        self.initial_cash = initial_cash
        self.commission = commission
        self.slippage = slippage

    def run(
        self,
        data_file: str,
        strategy_cls: Type[bt.Strategy],
    ) -> dict:
        """运行回测。

        Args:
            data_file: 数据文件路径（CSV或Parquet）
            strategy_cls: 策略类

        Returns:
            包含回测结果的字典
        """
        # 加载数据
        data_feed = BacktraderDataLoader.load_from_file(data_file)

        # 创建Cerebro
        cerebro = bt.Cerebro()
        cerebro.adddata(data_feed)
        cerebro.broker.setcash(self.initial_cash)
        cerebro.broker.setcommission(commission=self.commission)
        if self.slippage:
            cerebro.broker.set_slippage_perc(perc=self.slippage)
        cerebro.addstrategy(strategy_cls)

        # 运行回测
        cerebro.run()

        # 收集结果
        final_value = cerebro.broker.getvalue()
        initial_cash = self.initial_cash
        return {
            'initial_cash': initial_cash,
            'final_value': final_value,
            'return_pct': (final_value / initial_cash - 1) * 100,
        }

