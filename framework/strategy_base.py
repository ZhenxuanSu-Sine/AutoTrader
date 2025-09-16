"""
Generic strategy base classes and helper functions for Backtrader.

This module defines a `BaseStrategy` class that inherits from
``backtrader.Strategy`` and adds some convenience methods for logging
and order management.  It is meant to be extended by specific trading
strategies implemented in the `decision` package.
"""

import datetime
from typing import Optional

import backtrader as bt


class BaseStrategy(bt.Strategy):
    """Base class for strategies.

    Provides a simple logging facility and tracking of orders.  The
    derived classes are expected to override the ``next`` method to
    implement their trading logic.  Orders placed through this class
    will be tracked so that we can avoid sending duplicate orders or
    closing positions inadvertently.
    """

    params = dict(
        printlog=True,
    )

    def __init__(self) -> None:
        # To keep track of pending orders
        self.order: Optional[bt.Order] = None

    def log(self, txt: str, dt: Optional[datetime.datetime] = None) -> None:
        """Logging function for this strategy.

        Args:
            txt: The message to log.
            dt: The datetime to associate with the log entry.  If not
                provided, the current datetime from the data feed will
                be used.
        """
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.datetime(0)
            print(f'{dt.isoformat()} - {txt}')

    def notify_order(self, order: bt.Order) -> None:
        """Called by Backtrader for each order status change."""
        if order.status in [order.Submitted, order.Accepted]:
            # Order submitted/accepted to/by broker - nothing to do
            return

        # If we get here, the order has been completed, rejected or
        # cancelled.
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY EXECUTED, Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Commission: {order.executed.comm:.2f}'
                )
            else:  # sell
                self.log(
                    f'SELL EXECUTED, Price: {order.executed.price:.2f}, '
                    f'Cost: {order.executed.value:.2f}, '
                    f'Commission: {order.executed.comm:.2f}'
                )
            # Indicate that the order has been completed
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected: {order}')

        # Reset orders
        self.order = None

    def notify_trade(self, trade: bt.Trade) -> None:
        """Called by Backtrader when a trade (entry/exit) is closed."""
        if not trade.isclosed:
            return
        self.log(
            f'TRADE PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}'
        )

    def stop(self) -> None:
        """Called when the strategy stops.  Override in subclasses to log final state."""
        self.log(
            f'(Ending Value {self.broker.getvalue():.2f})'
        )