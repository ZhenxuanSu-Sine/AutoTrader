"""
Backtest evaluator.

This module defines a command‑line interface for running simple backtests
using Backtrader.  Given a CSV file containing OHLCV data and a
strategy name, the script loads the data into a PandasData feed,
instantiates the requested strategy and executes the backtest.  It
prints the final portfolio value and basic performance statistics to
stdout.
"""

import argparse
import importlib
from typing import Dict, Type

import backtrader as bt
import pandas as pd


def load_strategy(name: str) -> Type[bt.Strategy]:
    """Dynamically import and return the strategy class.

    Strategies are expected to live in the ``decision`` package and
    follow the naming convention ``<Name>Strategy`` (camel case).  The
    mapping below allows simple short names such as ``buy_hold`` or
    ``random``.  New strategies can be registered here.

    Args:
        name: Short name of the strategy.

    Returns:
        A subclass of ``bt.Strategy``.

    Raises:
        KeyError: If the strategy name is not recognised.
    """
    mapping: Dict[str, str] = {
        'buy_hold': 'buy_and_hold.BuyAndHoldStrategy',
        'random': 'random_trader.RandomTraderStrategy',
    }
    if name not in mapping:
        raise KeyError(f'Unknown strategy: {name}')
    module_name, class_name = mapping[name].rsplit('.', 1)
    module = importlib.import_module(f'decision.{module_name}')
    return getattr(module, class_name)


def run_backtest(
    data_file: str,
    strategy_cls: Type[bt.Strategy],
    initial_cash: float = 100_000.0,
    commission: float = 0.001,
    slippage: float = 0.0,
) -> float:
    """Run a single backtest and return final portfolio value.

    Args:
        data_file: Path to a CSV file containing columns
            ``datetime``, ``open``, ``high``, ``low``, ``close``, ``volume``.
        strategy_cls: Strategy class to run.
        initial_cash: Starting capital for the broker.
        commission: Commission rate (proportion of trade value).
        slippage: Slippage rate (proportion of price per trade).

    Returns:
        The final value of the broker after running the backtest.
    """
    # Read data
    df = pd.read_csv(data_file, parse_dates=['datetime'])
    df = df.sort_values('datetime')
    data_feed = bt.feeds.PandasData(dataname=df, datetime='datetime')

    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    if slippage:
        # Apply fixed percentage slippage to all trades
        cerebro.broker.set_slippage_perc(perc=slippage)
    cerebro.addstrategy(strategy_cls)

    # Run and return final value
    cerebro.run()
    final_value = cerebro.broker.getvalue()
    return final_value


def main() -> None:
    parser = argparse.ArgumentParser(description='Run a Backtrader backtest.')
    parser.add_argument('--data-file', required=True, help='Path to CSV file with OHLCV data')
    parser.add_argument('--strategy', required=True, help='Name of the strategy (buy_hold, random)')
    parser.add_argument('--capital', type=float, default=100_000.0, help='Initial capital')
    parser.add_argument('--commission', type=float, default=0.001, help='Commission as fraction of trade value')
    parser.add_argument('--slippage', type=float, default=0.0, help='Slippage rate (optional)')
    args = parser.parse_args()

    strategy_cls = load_strategy(args.strategy)
    final_value = run_backtest(
        data_file=args.data_file,
        strategy_cls=strategy_cls,
        initial_cash=args.capital,
        commission=args.commission,
        slippage=args.slippage,
    )
    # Print results
    print(f'Strategy {args.strategy!r} final portfolio value: {final_value:.2f}')
    print(f'Return on capital: {(final_value / args.capital - 1) * 100:.2f}%')


if __name__ == '__main__':
    main()