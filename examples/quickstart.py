"""Offline end-to-end demo: synthetic bars -> strategy -> backtest -> factor report."""

from __future__ import annotations

import numpy as np
import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.core import CostModel
from autotrader.factors import evaluate_factor, momentum
from autotrader.strategies import moving_average_weights


def sample_bars() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2023-01-02", periods=160, freq="B")
    frames = []
    for symbol, drift in (("600000", 0.0004), ("000001", 0.0002)):
        close = 10 * np.exp(np.cumsum(rng.normal(drift, 0.012, len(dates))))
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": dates,
                    "symbol": symbol,
                    "open": close * (1 + rng.normal(0, 0.002, len(dates))),
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": rng.integers(100_000, 1_000_000, len(dates)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    bars = sample_bars()
    weights = moving_average_weights(bars, fast=5, slow=20, weight=0.45)
    engine = PortfolioEngine(
        BacktestConfig(initial_cash=1_000_000, cost=CostModel(minimum_commission=0))
    )
    result = engine.run(bars, weights)
    report = evaluate_factor(momentum(bars, 20), bars, periods=5)
    print("Backtest:", result.metrics)
    print("Factor:", report.summary)

