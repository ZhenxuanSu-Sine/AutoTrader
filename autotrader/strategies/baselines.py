"""Simple strategies used to verify the research pipeline."""

from __future__ import annotations

import pandas as pd

from autotrader.data.schema import normalize_bars


def buy_and_hold_weights(bars: pd.DataFrame, weight: float = 1.0) -> pd.DataFrame:
    if not 0 <= weight <= 1:
        raise ValueError("weight must be between 0 and 1")
    data = normalize_bars(bars)
    symbols = data["symbol"].drop_duplicates()
    if len(symbols) != 1:
        raise ValueError("buy_and_hold_weights expects exactly one symbol")
    first = data.iloc[0]
    return pd.DataFrame(
        {"timestamp": [first["timestamp"]], "symbol": [first["symbol"]], "weight": [weight]}
    )


def moving_average_weights(
    bars: pd.DataFrame,
    *,
    fast: int = 5,
    slow: int = 20,
    weight: float = 1.0,
) -> pd.DataFrame:
    """Long when trailing fast MA exceeds slow MA; no future data is used."""

    if not 0 < fast < slow:
        raise ValueError("expected 0 < fast < slow")
    if not 0 <= weight <= 1:
        raise ValueError("weight must be between 0 and 1")
    data = normalize_bars(bars)
    grouped = data.groupby("symbol", sort=False)["close"]
    data["fast"] = grouped.transform(lambda values: values.rolling(fast).mean())
    data["slow"] = grouped.transform(lambda values: values.rolling(slow).mean())
    data["weight"] = (data["fast"] > data["slow"]).astype(float) * weight
    return data[["timestamp", "symbol", "weight"]]


def time_series_momentum_weights(
    bars: pd.DataFrame, *, lookback: int = 60, weight: float = 1.0
) -> pd.DataFrame:
    """Hold an asset when its trailing return is positive."""

    if lookback < 1:
        raise ValueError("lookback must be positive")
    if not 0 <= weight <= 1:
        raise ValueError("weight must be between 0 and 1")
    data = normalize_bars(bars)
    trailing = data.groupby("symbol", sort=False)["close"].pct_change(lookback)
    data["weight"] = (trailing > 0).astype(float) * weight
    return data[["timestamp", "symbol", "weight"]]


def equal_weight_weights(bars: pd.DataFrame) -> pd.DataFrame:
    """Buy all symbols at equal weight on the first complete timestamp."""

    data = normalize_bars(bars)
    symbols = sorted(data["symbol"].unique())
    counts = data.groupby("timestamp")["symbol"].nunique()
    complete = counts[counts == len(symbols)]
    if complete.empty:
        raise ValueError("bars have no timestamp shared by every symbol")
    timestamp = complete.index[0]
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "symbol": symbols,
            "weight": 1.0 / len(symbols),
        }
    )


def trend_equal_weight_weights(
    bars: pd.DataFrame, *, window: int = 100, rebalance: str = "monthly"
) -> pd.DataFrame:
    """Allocate 1/N to assets above their MA, rebalancing monthly by default."""

    if window < 2:
        raise ValueError("window must be at least 2")
    data = normalize_bars(bars)
    count = data["symbol"].nunique()
    average = data.groupby("symbol", sort=False)["close"].transform(
        lambda values: values.rolling(window).mean()
    )
    data["weight"] = (data["close"] > average).astype(float) / count
    if rebalance == "monthly":
        data["month"] = data["timestamp"].dt.to_period("M")
        rebalance_dates = data.groupby("month")["timestamp"].min()
        data = data[data["timestamp"].isin(rebalance_dates)]
    elif rebalance != "daily":
        raise ValueError("rebalance must be 'monthly' or 'daily'")
    return data[["timestamp", "symbol", "weight"]]


def cross_sectional_momentum_weights(
    bars: pd.DataFrame,
    *,
    lookback: int = 60,
    top_n: int = 2,
) -> pd.DataFrame:
    """On the first trading day each month, hold the strongest ``top_n`` assets."""

    if lookback < 1 or top_n < 1:
        raise ValueError("lookback and top_n must be positive")
    data = normalize_bars(bars)
    if top_n > data["symbol"].nunique():
        raise ValueError("top_n exceeds the number of symbols")
    data["momentum"] = data.groupby("symbol", sort=False)["close"].pct_change(lookback)
    data["month"] = data["timestamp"].dt.to_period("M")
    rebalance_dates = data.groupby("month")["timestamp"].min()
    selected = data[data["timestamp"].isin(rebalance_dates)].copy()
    selected["rank"] = selected.groupby("timestamp")["momentum"].rank(
        ascending=False, method="first"
    )
    selected["weight"] = (selected["rank"] <= top_n).astype(float) / top_n
    return selected[["timestamp", "symbol", "weight"]]
