"""A deterministic target-weight portfolio simulator for research.

Signals are observed at a bar close and executed at the next available bar's
open. This explicit one-bar delay is the main guard against look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from autotrader.core.models import CostModel
from autotrader.data.schema import normalize_bars
from autotrader.evaluation.metrics import backtest_metrics


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    lot_size: int = 100
    long_only: bool = True
    t_plus_one: bool = True
    annualization: int = 252
    liquidate_at_end: bool = False
    max_gross_exposure: float = 1.0
    annual_borrow_rate: float = 0.0
    cost: CostModel = field(default_factory=CostModel)

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.max_gross_exposure <= 0:
            raise ValueError("max_gross_exposure must be positive")
        if self.annual_borrow_rate < 0:
            raise ValueError("annual_borrow_rate must be non-negative")


@dataclass
class BacktestResult:
    equity: pd.DataFrame
    trades: pd.DataFrame
    positions: pd.DataFrame
    metrics: dict[str, float]


class PortfolioEngine:
    """Execute close-generated target weights at the next bar open."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(self, bars: pd.DataFrame, target_weights: pd.DataFrame) -> BacktestResult:
        data = normalize_bars(bars)
        weights = self._normalize_weights(target_weights)
        unknown_symbols = set(weights["symbol"]) - set(data["symbol"])
        if unknown_symbols:
            raise ValueError(f"target weights contain symbols absent from bars: {sorted(unknown_symbols)}")
        grouped = list(data.groupby("timestamp", sort=True))
        weights_by_time = {
            timestamp: dict(group[["symbol", "weight"]].itertuples(index=False, name=None))
            for timestamp, group in weights.groupby("timestamp", sort=False)
        }
        if len(grouped) < 2:
            raise ValueError("backtest requires at least two timestamps")

        cash = self.config.initial_cash
        holdings: dict[str, int] = {}
        sellable: dict[str, int] = {}
        previous_date = None
        pending: Mapping[str, float] = {}
        last_close: dict[str, float] = {}
        equity_rows: list[dict] = []
        position_rows: list[dict] = []
        trade_rows: list[dict] = []
        financing_cost = 0.0

        for bar_index, (timestamp, snapshot) in enumerate(grouped):
            snapshot = snapshot.set_index("symbol")
            trading_date = timestamp.date()
            if previous_date is None or trading_date != previous_date:
                if cash < 0 and previous_date is not None:
                    daily_financing = (
                        -cash * self.config.annual_borrow_rate / self.config.annualization
                    )
                    cash -= daily_financing
                    financing_cost += daily_financing
                sellable = holdings.copy()
                previous_date = trading_date

            if pending:
                cash = self._rebalance(
                    timestamp, snapshot, pending, cash, holdings, sellable, last_close, trade_rows
                )

            last_close.update(snapshot["close"].astype(float).to_dict())
            if self.config.liquidate_at_end and bar_index == len(grouped) - 1:
                cash = self._liquidate(
                    timestamp, snapshot, cash, holdings, sellable, last_close, trade_rows
                )
            close_value = sum(quantity * last_close[symbol] for symbol, quantity in holdings.items())
            total_equity = cash + close_value
            if total_equity <= 0:
                raise RuntimeError(f"portfolio became insolvent at {timestamp}")
            equity_rows.append(
                {
                    "timestamp": timestamp,
                    "cash": cash,
                    "equity": total_equity,
                    "financing_cost": financing_cost,
                }
            )
            for symbol, quantity in sorted(holdings.items()):
                if quantity:
                    position_rows.append(
                        {
                            "timestamp": timestamp,
                            "symbol": symbol,
                            "quantity": quantity,
                            "sellable": sellable.get(symbol, 0),
                            "close": float(snapshot.at[symbol, "close"]) if symbol in snapshot.index else np.nan,
                        }
                    )

            pending = weights_by_time.get(timestamp, {})

        equity = pd.DataFrame(equity_rows).set_index("timestamp")
        trades = pd.DataFrame(
            trade_rows,
            columns=[
                "timestamp", "symbol", "side", "quantity", "raw_price", "price",
                "notional", "fees", "slippage_cost", "reason",
            ],
        )
        positions = pd.DataFrame(
            position_rows, columns=["timestamp", "symbol", "quantity", "sellable", "close"]
        )
        return BacktestResult(
            equity=equity,
            trades=trades,
            positions=positions,
            metrics=backtest_metrics(
                equity["equity"], trades, self.config.annualization, financing_cost
            ),
        )

    def _rebalance(
        self,
        timestamp: pd.Timestamp,
        snapshot: pd.DataFrame,
        targets: Mapping[str, float],
        cash: float,
        holdings: dict[str, int],
        sellable: dict[str, int],
        last_close: Mapping[str, float],
        trades: list[dict],
    ) -> float:
        cost = self.config.cost
        open_equity = cash + sum(
            quantity
            * (
                float(snapshot.at[symbol, "open"])
                if symbol in snapshot.index
                else float(last_close[symbol])
            )
            for symbol, quantity in holdings.items()
        )
        symbols = set(holdings) | set(targets)
        desired: dict[str, int] = {}
        for symbol in symbols:
            if symbol not in snapshot.index:
                continue
            weight = float(targets.get(symbol, 0.0))
            price = float(snapshot.at[symbol, "open"])
            desired[symbol] = int(open_equity * weight / price / self.config.lot_size) * self.config.lot_size

        # Sell first so proceeds can fund buys. A-share T+1 limits sellable shares.
        for symbol in sorted(desired):
            current = holdings.get(symbol, 0)
            quantity = max(current - desired[symbol], 0)
            if self.config.t_plus_one:
                quantity = min(quantity, sellable.get(symbol, 0))
            if not quantity:
                continue
            raw_price = float(snapshot.at[symbol, "open"])
            price = raw_price * (1 - cost.slippage_rate)
            notional = price * quantity
            fees = cost.commission(notional) + notional * cost.stamp_duty_rate
            cash += notional - fees
            holdings[symbol] = current - quantity
            sellable[symbol] = max(sellable.get(symbol, 0) - quantity, 0)
            trades.append(
                self._trade(timestamp, symbol, "sell", quantity, raw_price, price, fees)
            )

        for symbol in sorted(desired):
            current = holdings.get(symbol, 0)
            wanted = max(desired[symbol] - current, 0)
            if not wanted:
                continue
            raw_price = float(snapshot.at[symbol, "open"])
            price = raw_price * (1 + cost.slippage_rate)
            affordable = self._affordable_quantity(cash, price, wanted)
            if not affordable:
                continue
            notional = price * affordable
            fees = cost.commission(notional)
            cash -= notional + fees
            holdings[symbol] = current + affordable
            if not self.config.t_plus_one:
                sellable[symbol] = sellable.get(symbol, 0) + affordable
            trades.append(
                self._trade(timestamp, symbol, "buy", affordable, raw_price, price, fees)
            )
        return cash

    def _liquidate(
        self,
        timestamp: pd.Timestamp,
        snapshot: pd.DataFrame,
        cash: float,
        holdings: dict[str, int],
        sellable: dict[str, int],
        last_close: Mapping[str, float],
        trades: list[dict],
    ) -> float:
        """Close all positions at the final close for isolated-window accounting.

        This terminal settlement deliberately overrides T+1. It represents the
        cost of ending the experiment in cash, rather than a live intraday order.
        """

        cost = self.config.cost
        for symbol in sorted(holdings):
            quantity = holdings.get(symbol, 0)
            if not quantity:
                continue
            raw_price = (
                float(snapshot.at[symbol, "close"])
                if symbol in snapshot.index
                else float(last_close[symbol])
            )
            price = raw_price * (1 - cost.slippage_rate)
            notional = price * quantity
            fees = cost.commission(notional) + notional * cost.stamp_duty_rate
            cash += notional - fees
            holdings[symbol] = 0
            sellable[symbol] = 0
            trades.append(
                self._trade(
                    timestamp,
                    symbol,
                    "sell",
                    quantity,
                    raw_price,
                    price,
                    fees,
                    reason="terminal_liquidation",
                )
            )
        return cash

    def _affordable_quantity(self, cash: float, price: float, wanted: int) -> int:
        if self.config.max_gross_exposure > 1:
            return wanted
        lots = wanted // self.config.lot_size
        while lots > 0:
            quantity = lots * self.config.lot_size
            if self.config.cost.buy_cash_required(price, quantity) <= cash + 1e-9:
                return quantity
            lots -= 1
        return 0

    @staticmethod
    def _trade(
        timestamp, symbol, side, quantity, raw_price, price, fees, reason="rebalance"
    ) -> dict:
        return {
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "raw_price": raw_price,
            "price": price,
            "notional": price * quantity,
            "fees": fees,
            "slippage_cost": abs(price - raw_price) * quantity,
            "reason": reason,
        }

    def _normalize_weights(self, weights: pd.DataFrame) -> pd.DataFrame:
        required = {"timestamp", "symbol", "weight"}
        if not required.issubset(weights.columns):
            raise ValueError(f"target_weights must contain {sorted(required)}")
        result = weights[["timestamp", "symbol", "weight"]].copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"])
        result["symbol"] = result["symbol"].astype("string")
        result["weight"] = pd.to_numeric(result["weight"], errors="raise")
        if result.duplicated(["timestamp", "symbol"]).any():
            raise ValueError("duplicate target weight")
        if self.config.long_only and (result["weight"] < 0).any():
            raise ValueError("negative weights are not allowed in long-only mode")
        gross = result.groupby("timestamp")["weight"].sum()
        if (gross > self.config.max_gross_exposure + 1e-9).any():
            raise ValueError(
                f"target weights exceed max gross exposure {self.config.max_gross_exposure:.2f}"
            )
        return result.sort_values(["timestamp", "symbol"])

    @staticmethod
    def _weights_at(weights: pd.DataFrame, timestamp: pd.Timestamp) -> dict[str, float]:
        rows = weights.loc[weights["timestamp"] == timestamp, ["symbol", "weight"]]
        return dict(rows.itertuples(index=False, name=None))
