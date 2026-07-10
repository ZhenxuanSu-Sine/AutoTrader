"""Generic target-weight risk overlays."""

from __future__ import annotations

import pandas as pd


def scale_weights(weights: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    """Scale target weights by a constant risk multiplier."""

    if multiplier < 0:
        raise ValueError("multiplier must be non-negative")
    result = weights[["timestamp", "symbol", "weight"]].copy()
    result["weight"] = result["weight"] * multiplier
    return result


def cap_gross_exposure(weights: pd.DataFrame, max_gross: float) -> pd.DataFrame:
    """Proportionally cap each timestamp's gross target exposure."""

    if max_gross <= 0:
        raise ValueError("max_gross must be positive")
    result = weights[["timestamp", "symbol", "weight"]].copy()
    gross = result["weight"].abs().groupby(result["timestamp"]).transform("sum")
    scale = (max_gross / gross.replace(0, pd.NA)).clip(upper=1).fillna(1)
    result["weight"] = result["weight"] * scale
    return result
