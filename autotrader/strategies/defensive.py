"""Defensive stock-selection strategies for broad A-share universes."""

from __future__ import annotations

import pandas as pd


def large_cap_low_vol_monthly_weights(
    monthly_features: pd.DataFrame,
    *,
    top_n: int = 50,
    liquidity_quantile: float = 0.40,
    cap_quantile: float = 0.40,
    low_vol_weight: float = 0.55,
    drawdown_weight: float = 0.25,
    cap_weight: float = 0.20,
    allocation: str = "cap",
) -> pd.DataFrame:
    """Select liquid, large-cap, low-volatility stocks from monthly features.

    Required columns are produced by ``scripts/build_csmar_monthly_features.py``.
    The default parameters correspond to the best confirmed CSMAR candidate so
    far: ``def_top50_liq0.40_capq0.40_cap``.
    """

    required = {
        "timestamp",
        "symbol",
        "history",
        "liquidity_20_rank",
        "float_market_cap",
        "float_market_cap_rank",
        "vol_60",
        "vol_60_rank",
        "drawdown_120_rank",
    }
    missing = required - set(monthly_features.columns)
    if missing:
        raise ValueError(f"monthly_features missing columns: {sorted(missing)}")
    if top_n < 1:
        raise ValueError("top_n must be positive")
    if not 0 <= liquidity_quantile <= 1 or not 0 <= cap_quantile <= 1:
        raise ValueError("quantiles must be in [0, 1]")
    total = low_vol_weight + drawdown_weight + cap_weight
    if total <= 0:
        raise ValueError("factor weights must sum to a positive value")

    data = monthly_features.copy()
    score = (
        data["vol_60_rank"] * low_vol_weight
        + data["drawdown_120_rank"] * drawdown_weight
        + data["float_market_cap_rank"] * cap_weight
    ) / total
    eligible = (
        (data["history"] >= 252)
        & (data["liquidity_20_rank"] >= liquidity_quantile)
        & (data["float_market_cap_rank"] >= cap_quantile)
        & score.notna()
    )
    rank = score.where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)

    if allocation == "cap":
        raw = data["float_market_cap"].where(selected, 0.0).clip(lower=0)
    elif allocation == "equal":
        raw = selected.astype(float)
    elif allocation == "inverse_vol":
        raw = (1 / data["vol_60"].replace(0, pd.NA)).where(selected, 0.0)
    else:
        raise ValueError("allocation must be cap, equal or inverse_vol")
    total_raw = raw.groupby(data["timestamp"]).transform("sum")
    data["weight"] = (raw / total_raw.replace(0, pd.NA)).fillna(0.0).astype(float)
    return data.loc[data["weight"] > 0, ["timestamp", "symbol", "weight"]].reset_index(drop=True)
