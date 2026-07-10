"""Leakage-safe baseline factors operating on canonical long-form bars."""

from __future__ import annotations

import pandas as pd

from autotrader.data.schema import normalize_bars


def momentum(bars: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Trailing close-to-close return; uses information through the current close."""

    if window < 1:
        raise ValueError("window must be positive")
    data = normalize_bars(bars)
    data["factor"] = data.groupby("symbol", sort=False)["close"].pct_change(window)
    return data[["timestamp", "symbol", "factor"]]


def rolling_volatility(bars: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Trailing standard deviation of close returns."""

    if window < 2:
        raise ValueError("window must be at least 2")
    data = normalize_bars(bars)
    returns = data.groupby("symbol", sort=False)["close"].pct_change()
    data["factor"] = (
        returns.groupby(data["symbol"], sort=False)
        .rolling(window, min_periods=window)
        .std()
        .reset_index(level=0, drop=True)
    )
    return data[["timestamp", "symbol", "factor"]]

