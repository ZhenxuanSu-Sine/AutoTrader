"""
Buy‑and‑hold strategy.

This trivial strategy simply buys a fixed quantity of shares at the
first opportunity and holds them until the end of the backtest.  It
demonstrates how to extend the ``BaseStrategy`` class and issue a
single order.  The size to buy is configurable via strategy
parameters.
"""

from typing import Optional

import backtrader as bt

from ..framework.strategy_base import BaseStrategy


class BuyAndHoldStrategy(BaseStrategy):
    """A very simple buy‑and‑hold strategy."""

    params = dict(
        size=1,
    )

    def __init__(self) -> None:
        super().__init__()
        # Flag to indicate whether we have already bought
        self.bought = False

    def next(self) -> None:
        # If an order is pending, do nothing
        if self.order:
            return

        # If we haven't bought yet, buy at market on the first data bar
        if not self.position and not self.bought:
            self.log(f'Placing buy order for {self.params.size} units')
            self.order = self.buy(size=self.params.size)
            self.bought = True
        # Otherwise, hold until the end of the backtest