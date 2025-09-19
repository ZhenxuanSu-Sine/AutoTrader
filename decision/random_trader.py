"""
Random trading strategy.

This example strategy demonstrates how to issue random buy and sell
orders on each bar.  It will generate trading signals with a 50/50
probability.  To avoid accidental short positions, the strategy will
only sell if a position is currently open.  Conversely, it will only
buy if no position is open.  The number of shares to trade is
configurable via the ``size`` parameter.
"""

import random

import backtrader as bt

from framework.strategy_base import BaseStrategy


class RandomTraderStrategy(BaseStrategy):
    """Strategy that trades randomly."""

    params = dict(
        size=1,
        buy_prob=0.5,  # probability of issuing a buy when flat
        sell_prob=0.5,  # probability of issuing a sell when long
    )

    def __init__(self) -> None:
        super().__init__()

    def next(self) -> None:
        if self.order:
            # Wait if there is a pending order
            return
        # We currently have no position, maybe buy
        if not self.position:
            if random.random() < self.params.buy_prob:
                self.log(f'Random buy {self.params.size} units')
                self.order = self.buy(size=self.params.size)
        else:
            # We have a position, maybe sell
            if random.random() < self.params.sell_prob:
                self.log(f'Random sell {self.position.size} units')
                self.order = self.sell(size=self.position.size)