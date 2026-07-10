"""CPU-friendly candidate strategies aimed at risk-adjusted returns.

All signals are causal: rolling statistics at timestamp t use rows at or before
t, while the portfolio engine executes them on the next available bar.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from autotrader.data.schema import normalize_bars


def _features(bars: pd.DataFrame, vol_window: int) -> pd.DataFrame:
    data = normalize_bars(bars)
    returns = data.groupby("symbol", sort=False)["close"].pct_change()
    data["volatility"] = (
        returns.groupby(data["symbol"], sort=False)
        .rolling(vol_window, min_periods=vol_window)
        .std()
        .reset_index(level=0, drop=True)
        * np.sqrt(252)
    )
    return data


def _rebalance_filter(data: pd.DataFrame, rebalance: str) -> pd.DataFrame:
    if rebalance == "daily":
        return data
    if rebalance == "weekly":
        period = data["timestamp"].dt.to_period("W-FRI")
    elif rebalance == "monthly":
        period = data["timestamp"].dt.to_period("M")
    else:
        raise ValueError("rebalance must be daily, weekly or monthly")
    first_dates = data.groupby(period)["timestamp"].min()
    return data[data["timestamp"].isin(first_dates)]


def _risk_weights(
    data: pd.DataFrame,
    raw_score: pd.Series,
    *,
    target_volatility: float | None,
    max_gross: float = 1.0,
) -> pd.Series:
    safe_vol = data["volatility"].replace(0, np.nan)
    raw = raw_score.clip(lower=0).fillna(0) / safe_vol
    total = raw.groupby(data["timestamp"]).transform("sum")
    base = (raw / total.replace(0, np.nan)).fillna(0)
    if target_volatility is None:
        return base * max_gross
    # Diagonal covariance approximation. It is intentionally conservative and
    # avoids unstable covariance inversion in a five-asset universe.
    component = base * safe_vol.fillna(0)
    estimated = np.sqrt(
        component.pow(2).groupby(data["timestamp"]).transform("sum")
    )
    scale = (target_volatility / estimated.replace(0, np.nan)).clip(upper=max_gross)
    return base * scale.fillna(0)


def multi_horizon_trend_weights(
    bars: pd.DataFrame,
    *,
    horizons: Sequence[int] = (20, 60, 120),
    vol_window: int = 20,
    target_volatility: float = 0.12,
    minimum_score: float = 0.5,
    rebalance: str = "weekly",
    max_gross: float = 1.0,
) -> pd.DataFrame:
    """Blend several trailing trend signs and scale inverse to volatility."""

    if not horizons or any(value < 1 for value in horizons):
        raise ValueError("horizons must be positive")
    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    components = [grouped.pct_change(period) for period in horizons]
    valid = pd.concat(components, axis=1).notna().all(axis=1)
    score = pd.concat([(value > 0).astype(float) for value in components], axis=1).mean(axis=1)
    score = score.where(valid & (score >= minimum_score), 0.0)
    data["weight"] = _risk_weights(
        data, score, target_volatility=target_volatility, max_gross=max_gross
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def dual_momentum_rotation_weights(
    bars: pd.DataFrame,
    *,
    lookback: int = 120,
    trend_window: int = 100,
    top_n: int = 2,
    vol_window: int = 20,
    target_volatility: float | None = 0.15,
    rebalance: str = "monthly",
    max_gross: float = 1.0,
) -> pd.DataFrame:
    """Select relative winners only when their absolute trend is positive."""

    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    data["momentum"] = grouped.pct_change(lookback)
    average = grouped.transform(lambda values: values.rolling(trend_window).mean())
    eligible = (data["momentum"] > 0) & (data["close"] > average)
    rank = data["momentum"].where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)
    # Inverse-volatility allocation is less sensitive to an extreme momentum
    # estimate than directly weighting by past return.
    data["weight"] = _risk_weights(
        data,
        selected.astype(float),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def defensive_composite_weights(
    bars: pd.DataFrame,
    *,
    momentum_windows: Sequence[int] = (60, 120),
    trend_window: int = 100,
    drawdown_window: int = 120,
    vol_window: int = 40,
    top_n: int = 3,
    target_volatility: float | None = 0.12,
    rebalance: str = "monthly",
    max_gross: float = 1.0,
) -> pd.DataFrame:
    """Combine momentum, low volatility and shallow drawdown ranks."""

    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    rank_parts = []
    for window in momentum_windows:
        momentum = grouped.pct_change(window)
        rank_parts.append(momentum.groupby(data["timestamp"]).rank(pct=True))
    low_vol_rank = data["volatility"].groupby(data["timestamp"]).rank(
        ascending=False, pct=True
    )
    rolling_high = grouped.transform(lambda values: values.rolling(drawdown_window).max())
    drawdown = data["close"] / rolling_high - 1
    drawdown_rank = drawdown.groupby(data["timestamp"]).rank(pct=True)
    composite = pd.concat(rank_parts + [low_vol_rank, drawdown_rank], axis=1).mean(axis=1)
    average = grouped.transform(lambda values: values.rolling(trend_window).mean())
    eligible = data["close"] > average
    rank = composite.where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)
    data["weight"] = _risk_weights(
        data,
        composite.where(selected, 0.0),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def breadth_regime_weights(
    bars: pd.DataFrame,
    *,
    trend_window: int = 100,
    breadth_threshold: float = 0.6,
    vol_window: int = 20,
    target_volatility: float | None = 0.12,
    rebalance: str = "weekly",
    max_gross: float = 1.0,
) -> pd.DataFrame:
    """Take inverse-volatility exposure only in a broad positive-trend regime."""

    data = _features(bars, vol_window)
    average = data.groupby("symbol", sort=False)["close"].transform(
        lambda values: values.rolling(trend_window).mean()
    )
    positive = data["close"] > average
    breadth = positive.groupby(data["timestamp"]).transform("mean")
    eligible = positive & (breadth >= breadth_threshold)
    data["weight"] = _risk_weights(
        data,
        eligible.astype(float),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def multifactor_stock_selection_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 5,
    momentum_windows: Sequence[int] = (20, 60, 120),
    vol_window: int = 60,
    drawdown_window: int = 120,
    liquidity_window: int = 20,
    liquidity_quantile: float = 0.3,
    trend_window: int = 100,
    minimum_history: int = 252,
    momentum_weight: float = 0.5,
    low_vol_weight: float = 0.25,
    drawdown_weight: float = 0.25,
    target_volatility: float | None = 0.12,
    rebalance: str = "monthly",
    max_gross: float = 1.0,
    require_trend: bool = True,
) -> pd.DataFrame:
    """Select stocks using causal momentum, volatility, drawdown and liquidity.

    The universe itself must be supplied point-in-time by the caller. This
    function only ranks securities present in ``bars`` at each timestamp.
    """

    if top_n < 1 or minimum_history < 2:
        raise ValueError("top_n must be positive and minimum_history at least 2")
    if not 0 <= liquidity_quantile < 1:
        raise ValueError("liquidity_quantile must be in [0, 1)")
    factor_total = momentum_weight + low_vol_weight + drawdown_weight
    if factor_total <= 0:
        raise ValueError("factor weights must sum to a positive value")

    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    momentum_ranks = []
    for window in momentum_windows:
        momentum = grouped.pct_change(window)
        momentum_ranks.append(momentum.groupby(data["timestamp"]).rank(pct=True))
    momentum_score = pd.concat(momentum_ranks, axis=1).mean(axis=1)
    low_vol_score = data["volatility"].groupby(data["timestamp"]).rank(
        ascending=False, pct=True
    )
    rolling_high = grouped.transform(lambda values: values.rolling(drawdown_window).max())
    drawdown = data["close"] / rolling_high - 1
    drawdown_score = drawdown.groupby(data["timestamp"]).rank(pct=True)
    data["score"] = (
        momentum_score * momentum_weight
        + low_vol_score * low_vol_weight
        + drawdown_score * drawdown_weight
    ) / factor_total

    history = grouped.transform(lambda values: values.rolling(minimum_history).count())
    trend_average = grouped.transform(lambda values: values.rolling(trend_window).mean())
    if "amount" in data:
        liquidity = data.groupby("symbol", sort=False)["amount"].transform(
            lambda values: values.rolling(liquidity_window).mean()
        )
    else:
        liquidity = data.groupby("symbol", sort=False)["volume"].transform(
            lambda values: values.rolling(liquidity_window).mean()
        )
    liquidity_rank = liquidity.groupby(data["timestamp"]).rank(pct=True)
    trend_ok = (data["close"] > trend_average) if require_trend else pd.Series(
        True, index=data.index
    )
    eligible = (
        (history >= minimum_history)
        & trend_ok
        & (liquidity_rank >= liquidity_quantile)
        & data["score"].notna()
    )
    selection_rank = data["score"].where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (selection_rank <= top_n)
    data["weight"] = _risk_weights(
        data,
        data["score"].where(selected, 0.0),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def breakout_stock_selection_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 3,
    breakout_window: int = 60,
    momentum_window: int = 20,
    trend_window: int = 100,
    vol_window: int = 20,
    volume_window: int = 20,
    breakout_buffer: float = 0.03,
    minimum_history: int = 120,
    target_volatility: float | None = 0.24,
    max_gross: float = 1.5,
    rebalance: str = "weekly",
) -> pd.DataFrame:
    """Concentrate in liquid stocks near new highs with positive momentum."""

    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    momentum = grouped.pct_change(momentum_window)
    rolling_high = grouped.transform(lambda values: values.rolling(breakout_window).max())
    trend_average = grouped.transform(lambda values: values.rolling(trend_window).mean())
    history = grouped.transform(lambda values: values.rolling(minimum_history).count())
    volume_average = data.groupby("symbol", sort=False)["volume"].transform(
        lambda values: values.rolling(volume_window).mean()
    )
    volume_strength = data["volume"] / volume_average.replace(0, np.nan)
    proximity = data["close"] / rolling_high
    eligible = (
        (history >= minimum_history)
        & (proximity >= 1 - breakout_buffer)
        & (data["close"] > trend_average)
        & (momentum > 0)
    )
    momentum_rank = momentum.groupby(data["timestamp"]).rank(pct=True)
    volume_rank = volume_strength.groupby(data["timestamp"]).rank(pct=True)
    score = 0.75 * momentum_rank + 0.25 * volume_rank
    rank = score.where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)
    data["weight"] = _risk_weights(
        data,
        score.where(selected, 0.0),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def sparse_breakout_trend_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 3,
    breakout_window: int = 40,
    momentum_windows: Sequence[int] = (5, 10, 20),
    trend_window: int = 60,
    vol_window: int = 20,
    volume_window: int = 20,
    breakout_buffer: float = 0.02,
    minimum_momentum: float = 0.03,
    volume_multiple: float = 1.2,
    maximum_volatility: float | None = 0.75,
    minimum_history: int = 120,
    target_volatility: float | None = 0.25,
    max_gross: float = 2.0,
    rebalance: str = "weekly",
) -> pd.DataFrame:
    """Sparse short-term trend catcher.

    The signal only buys stocks that are close to recent highs, already above a
    medium trend average, showing positive short-term momentum and confirming
    volume. On rebalance dates without qualifying stocks it emits zero weights,
    so the portfolio engine exits existing positions.
    """

    if top_n < 1 or not momentum_windows:
        raise ValueError("top_n and momentum_windows must be positive")
    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    rolling_high = grouped.transform(lambda values: values.rolling(breakout_window).max())
    trend_average = grouped.transform(lambda values: values.rolling(trend_window).mean())
    history = grouped.transform(lambda values: values.rolling(minimum_history).count())
    momentum_parts = [grouped.pct_change(window) for window in momentum_windows]
    momentum_frame = pd.concat(momentum_parts, axis=1)
    momentum_score = momentum_frame.mean(axis=1)
    short_momentum = momentum_parts[0]
    medium_momentum = momentum_parts[-1]
    volume_average = data.groupby("symbol", sort=False)["volume"].transform(
        lambda values: values.rolling(volume_window).mean()
    )
    volume_strength = data["volume"] / volume_average.replace(0, np.nan)
    proximity = data["close"] / rolling_high
    eligible = (
        (history >= minimum_history)
        & (proximity >= 1 - breakout_buffer)
        & (data["close"] > trend_average)
        & (short_momentum > 0)
        & (medium_momentum >= minimum_momentum)
        & (volume_strength >= volume_multiple)
        & momentum_score.notna()
    )
    if maximum_volatility is not None:
        eligible &= data["volatility"] <= maximum_volatility

    momentum_rank = momentum_score.groupby(data["timestamp"]).rank(pct=True)
    proximity_rank = proximity.groupby(data["timestamp"]).rank(pct=True)
    volume_rank = volume_strength.groupby(data["timestamp"]).rank(pct=True)
    low_vol_rank = data["volatility"].groupby(data["timestamp"]).rank(
        ascending=False, pct=True
    )
    score = 0.45 * momentum_rank + 0.30 * proximity_rank + 0.15 * volume_rank + 0.10 * low_vol_rank
    rank = score.where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)
    data["weight"] = _risk_weights(
        data,
        score.where(selected, 0.0),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def contraction_breakout_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 3,
    breakout_window: int = 40,
    contraction_short_window: int = 10,
    contraction_long_window: int = 60,
    contraction_ratio: float = 0.75,
    momentum_window: int = 10,
    trend_window: int = 60,
    vol_window: int = 20,
    breakout_buffer: float = 0.01,
    minimum_history: int = 120,
    target_volatility: float | None = 0.25,
    max_gross: float = 2.0,
    rebalance: str = "weekly",
) -> pd.DataFrame:
    """Buy breakouts after volatility/range contraction.

    This is a simple CPU-friendly proxy for VCP/NR-style setups: recent
    realized volatility must be lower than the longer context, then price must
    press against a rolling high with positive momentum.
    """

    if top_n < 1:
        raise ValueError("top_n must be positive")
    data = _features(bars, vol_window)
    grouped = data.groupby("symbol", sort=False)["close"]
    returns = grouped.pct_change()
    short_vol = (
        returns.groupby(data["symbol"], sort=False)
        .rolling(contraction_short_window, min_periods=contraction_short_window)
        .std()
        .reset_index(level=0, drop=True)
    )
    long_vol = (
        returns.groupby(data["symbol"], sort=False)
        .rolling(contraction_long_window, min_periods=contraction_long_window)
        .std()
        .reset_index(level=0, drop=True)
    )
    contraction = short_vol / long_vol.replace(0, np.nan)
    rolling_high = grouped.transform(lambda values: values.rolling(breakout_window).max())
    trend_average = grouped.transform(lambda values: values.rolling(trend_window).mean())
    history = grouped.transform(lambda values: values.rolling(minimum_history).count())
    momentum = grouped.pct_change(momentum_window)
    proximity = data["close"] / rolling_high
    eligible = (
        (history >= minimum_history)
        & (contraction <= contraction_ratio)
        & (proximity >= 1 - breakout_buffer)
        & (data["close"] > trend_average)
        & (momentum > 0)
    )
    momentum_rank = momentum.groupby(data["timestamp"]).rank(pct=True)
    proximity_rank = proximity.groupby(data["timestamp"]).rank(pct=True)
    contraction_rank = contraction.groupby(data["timestamp"]).rank(ascending=True, pct=True)
    score = 0.45 * momentum_rank + 0.35 * proximity_rank + 0.20 * contraction_rank
    rank = score.where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)
    data["weight"] = _risk_weights(
        data,
        score.where(selected, 0.0),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    data = _rebalance_filter(data, rebalance)
    return data[["timestamp", "symbol", "weight"]]


def blend_weights(*frames: pd.DataFrame) -> pd.DataFrame:
    """Average multiple target-weight signals without introducing leverage."""

    if not frames:
        raise ValueError("at least one weight frame is required")
    indexed = []
    for number, frame in enumerate(frames):
        item = frame[["timestamp", "symbol", "weight"]].copy()
        item = item.rename(columns={"weight": f"weight_{number}"}).set_index(
            ["timestamp", "symbol"]
        )
        indexed.append(item)
    combined = pd.concat(indexed, axis=1).fillna(0)
    combined["weight"] = combined.mean(axis=1)
    return combined[["weight"]].reset_index()


def weighted_blend_weights(
    frames: Sequence[pd.DataFrame], allocations: Sequence[float]
) -> pd.DataFrame:
    """Combine sleeves with explicit capital allocations; missing sleeves stay cash."""

    if len(frames) != len(allocations) or not frames:
        raise ValueError("frames and allocations must have equal non-zero length")
    if any(value < 0 for value in allocations):
        raise ValueError("allocations must be non-negative")
    indexed = []
    for number, (frame, allocation) in enumerate(zip(frames, allocations)):
        item = frame[["timestamp", "symbol", "weight"]].copy()
        item[f"weight_{number}"] = item.pop("weight") * allocation
        indexed.append(item.set_index(["timestamp", "symbol"]))
    combined = pd.concat(indexed, axis=1).fillna(0)
    combined["weight"] = combined.sum(axis=1)
    return combined[["weight"]].reset_index()
