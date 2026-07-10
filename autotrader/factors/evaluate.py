"""Cross-sectional factor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from autotrader.data.schema import normalize_bars


@dataclass
class FactorReport:
    summary: dict[str, float]
    daily_ic: pd.Series
    quantile_returns: pd.DataFrame


def forward_returns(bars: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Return from current close to a future close, grouped by symbol."""

    if periods < 1:
        raise ValueError("periods must be positive")
    data = normalize_bars(bars)
    future = data.groupby("symbol", sort=False)["close"].shift(-periods)
    data["forward_return"] = future / data["close"] - 1
    return data[["timestamp", "symbol", "forward_return"]]


def evaluate_factor(
    factor: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    periods: int = 1,
    quantiles: int = 5,
) -> FactorReport:
    """Evaluate rank IC and equal-weight quantile forward returns.

    Factor values must be observable at ``timestamp``. Forward returns begin at
    that close, so execution-oriented tests should lag the factor separately.
    """

    required = {"timestamp", "symbol", "factor"}
    if not required.issubset(factor.columns):
        raise ValueError(f"factor must contain {sorted(required)}")
    if quantiles < 2:
        raise ValueError("quantiles must be at least 2")

    values = factor[["timestamp", "symbol", "factor"]].copy()
    values["timestamp"] = pd.to_datetime(values["timestamp"])
    values["symbol"] = values["symbol"].astype("string")
    values["factor"] = pd.to_numeric(values["factor"], errors="coerce")
    merged = values.merge(forward_returns(bars, periods), on=["timestamp", "symbol"])
    merged = merged.dropna(subset=["factor", "forward_return"])
    if merged.empty:
        raise ValueError("factor and forward returns have no overlapping observations")

    daily_ic = merged.groupby("timestamp").apply(
        lambda group: group["factor"].corr(group["forward_return"], method="spearman"),
        include_groups=False,
    ).dropna()

    def assign_quantile(group: pd.DataFrame) -> pd.Series:
        ranks = group["factor"].rank(method="first")
        count = min(quantiles, len(group))
        if count < 2:
            return pd.Series(np.nan, index=group.index)
        return pd.qcut(ranks, count, labels=False, duplicates="drop") + 1

    merged["quantile"] = merged.groupby("timestamp", group_keys=False).apply(
        assign_quantile, include_groups=False
    )
    quantile_returns = merged.dropna(subset=["quantile"]).pivot_table(
        index="timestamp", columns="quantile", values="forward_return", aggfunc="mean"
    )
    ic_std = float(daily_ic.std(ddof=1)) if len(daily_ic) > 1 else 0.0
    mean_ic = float(daily_ic.mean()) if len(daily_ic) else float("nan")
    summary = {
        "mean_rank_ic": mean_ic,
        "ic_std": ic_std,
        "ic_ir": mean_ic / ic_std if ic_std > 0 else 0.0,
        "positive_ic_ratio": float((daily_ic > 0).mean()) if len(daily_ic) else float("nan"),
        "observations": float(len(merged)),
    }
    if not quantile_returns.empty and len(quantile_returns.columns) >= 2:
        low, high = min(quantile_returns.columns), max(quantile_returns.columns)
        summary["top_bottom_spread"] = float(
            (quantile_returns[high] - quantile_returns[low]).mean()
        )
    return FactorReport(summary, daily_ic, quantile_returns)

