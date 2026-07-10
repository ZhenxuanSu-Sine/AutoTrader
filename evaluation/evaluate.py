"""
回测评估命令行接口。

提供命令行接口来运行回测，使用重构后的模块化组件。
"""

import argparse
import importlib
from typing import Dict, Type

import backtrader as bt

from evaluation.backtest import BacktestEngine
from evaluation.metrics import print_results


def load_strategy(name: str) -> Type[bt.Strategy]:
    """动态导入并返回策略类。

    策略类应该位于``decision``包中，遵循命名约定``<Name>Strategy``（驼峰命名）。
    下面的映射允许使用简单的短名称，如``buy_hold``或``random``。
    新策略可以在这里注册。

    Args:
        name: 策略的短名称。

    Returns:
        ``bt.Strategy``的子类。

    Raises:
        KeyError: 如果策略名称不被识别。
    """
    mapping: Dict[str, str] = {
        'buy_hold': 'buy_and_hold.BuyAndHoldStrategy',
        'random': 'random_trader.RandomTraderStrategy',
    }
    if name not in mapping:
        raise KeyError(f'未知策略: {name}')
    module_name, class_name = mapping[name].rsplit('.', 1)
    module = importlib.import_module(f'decision.{module_name}')
    return getattr(module, class_name)


def main() -> None:
    parser = argparse.ArgumentParser(description='运行Backtrader回测。')
    parser.add_argument('--data-file', required=True, help='包含OHLCV数据的CSV或Parquet文件路径')
    parser.add_argument('--strategy', required=True, help='策略名称 (buy_hold, random)')
    parser.add_argument('--capital', type=float, default=100_000.0, help='初始资金')
    parser.add_argument('--commission', type=float, default=0.001, help='手续费率（交易金额的比例）')
    parser.add_argument('--slippage', type=float, default=0.0, help='滑点率（可选）')
    args = parser.parse_args()

    # 加载策略
    strategy_cls = load_strategy(args.strategy)

    # 创建回测引擎并运行
    engine = BacktestEngine(
        initial_cash=args.capital,
        commission=args.commission,
        slippage=args.slippage,
    )
    results = engine.run(args.data_file, strategy_cls)

    # 打印结果
    print_results(args.strategy, results)


if __name__ == '__main__':
    main()