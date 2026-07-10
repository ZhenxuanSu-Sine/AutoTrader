"""Monthly CPU-friendly cross-sectional ML stock selection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


DEFAULT_FEATURE_COLUMNS = (
    "ret_5_rank",
    "ret_20_rank",
    "ret_60_rank",
    "ret_120_rank",
    "vol_20_rank",
    "vol_60_rank",
    "drawdown_120_rank",
    "liquidity_20_rank",
    "float_market_cap_rank",
    "total_market_cap_rank",
)


@dataclass(frozen=True)
class MonthlyMLConfig:
    """Configuration for causal monthly cross-sectional prediction."""

    model_type: str = "ridge"
    feature_columns: Sequence[str] = DEFAULT_FEATURE_COLUMNS
    train_window_months: int = 84
    min_train_months: int = 36
    min_train_observations: int = 20_000
    top_n: int = 50
    liquidity_quantile: float = 0.40
    cap_quantile: float = 0.40
    allocation: str = "cap"
    prediction_weight: float = 0.70
    cap_weight: float = 0.30
    random_state: int = 42


def _make_model(model_type: str, random_state: int):
    if model_type == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(StandardScaler(), Ridge(alpha=3.0))
    if model_type == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=15,
            l2_regularization=0.05,
            random_state=random_state,
        )
    raise ValueError("model_type must be ridge or hist_gradient_boosting")


def monthly_ml_prediction_weights(
    monthly_features: pd.DataFrame,
    config: MonthlyMLConfig | None = None,
    *,
    return_predictions: bool = False,
) -> pd.DataFrame:
    """Train a rolling monthly model and convert predictions to target weights.

    The label for a row at timestamp ``t`` is the stock's next monthly return.
    For a prediction timestamp ``T``, training rows are restricted to labels
    whose next-month timestamp is strictly before ``T``. This is intentionally
    conservative because the CSMAR feature file rebalances on the first trading
    day of a month.
    """

    cfg = config or MonthlyMLConfig()
    required = {
        "timestamp",
        "symbol",
        "close",
        "history",
        "liquidity_20_rank",
        "float_market_cap",
        "float_market_cap_rank",
        "vol_60",
        *cfg.feature_columns,
    }
    missing = required - set(monthly_features.columns)
    if missing:
        raise ValueError(f"monthly_features missing columns: {sorted(missing)}")
    if cfg.top_n < 1:
        raise ValueError("top_n must be positive")
    if cfg.train_window_months < cfg.min_train_months:
        raise ValueError("train_window_months must be >= min_train_months")

    data = monthly_features.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["label_timestamp"] = grouped["timestamp"].shift(-1)
    data["future_return"] = grouped["close"].shift(-1) / data["close"] - 1
    data = data.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    data["future_rank"] = data["future_return"].groupby(data["label_timestamp"]).rank(
        pct=True, method="average"
    )

    feature_columns = list(cfg.feature_columns)
    data["feature_complete"] = data[feature_columns].notna().all(axis=1)
    dates = pd.Index(sorted(data["timestamp"].drop_duplicates()))
    rows: list[pd.DataFrame] = []

    for index, timestamp in enumerate(dates):
        if index < cfg.min_train_months:
            continue
        train_start = dates[max(0, index - cfg.train_window_months)]
        train = data[
            (data["timestamp"] >= train_start)
            & (data["label_timestamp"] < timestamp)
            & data["feature_complete"]
            & data["future_rank"].notna()
        ]
        if len(train) < cfg.min_train_observations:
            continue
        current = data[
            (data["timestamp"] == timestamp)
            & data["feature_complete"]
            & (data["history"] >= 252)
            & (data["liquidity_20_rank"] >= cfg.liquidity_quantile)
            & (data["float_market_cap_rank"] >= cfg.cap_quantile)
        ].copy()
        if current.empty:
            continue

        model = _make_model(cfg.model_type, cfg.random_state)
        model.fit(train[feature_columns], train["future_rank"])
        current["prediction"] = model.predict(current[feature_columns])
        pred_rank = current["prediction"].rank(pct=True, method="first")
        score = cfg.prediction_weight * pred_rank + cfg.cap_weight * current["float_market_cap_rank"]
        current["score"] = score
        selected_rank = score.rank(ascending=False, method="first")
        selected = selected_rank <= cfg.top_n

        if cfg.allocation == "equal":
            raw = selected.astype(float)
        elif cfg.allocation == "cap":
            raw = current["float_market_cap"].where(selected, 0.0).clip(lower=0)
        elif cfg.allocation == "inverse_vol":
            raw = (1 / current["vol_60"].replace(0, np.nan)).where(selected, 0.0)
        elif cfg.allocation == "score":
            raw = score.where(selected, 0.0).clip(lower=0)
        else:
            raise ValueError("allocation must be cap, equal, inverse_vol or score")

        total = raw.sum()
        if total <= 0:
            continue
        current["weight"] = raw / total
        columns = ["timestamp", "symbol", "weight"]
        if return_predictions:
            columns.extend(["prediction", "score"])
        rows.append(current.loc[current["weight"] > 0, columns])

    if not rows:
        columns = ["timestamp", "symbol", "weight"]
        if return_predictions:
            columns.extend(["prediction", "score"])
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)
