"""CPU-friendly machine-learning strategies.

The functions here deliberately use rolling, point-in-time training. A feature
row at timestamp t is observable at that close; its label is only available
after ``prediction_horizon`` future closes. When predicting at date T, the
training set is restricted to rows whose labels would already be known by T.
The portfolio engine still executes generated targets on the next bar open.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from autotrader.data.schema import normalize_bars
from autotrader.strategies.high_sharpe import _rebalance_filter, _risk_weights


@dataclass(frozen=True)
class MLFeatureConfig:
    prediction_horizon: int = 5
    return_windows: Sequence[int] = (1, 3, 5, 10, 20, 60)
    volatility_windows: Sequence[int] = (5, 20)
    trend_windows: Sequence[int] = (20, 60)
    volume_window: int = 20
    drawdown_window: int = 60


def ml_feature_frame(bars: pd.DataFrame, config: MLFeatureConfig | None = None) -> pd.DataFrame:
    """Create causal features and future-return labels for ML research."""

    cfg = config or MLFeatureConfig()
    if cfg.prediction_horizon < 1:
        raise ValueError("prediction_horizon must be positive")
    data = normalize_bars(bars)
    grouped = data.groupby("symbol", sort=False)
    close = grouped["close"]
    returns = close.pct_change()
    feature_columns: list[str] = []

    for window in cfg.return_windows:
        name = f"ret_{window}"
        data[name] = close.pct_change(window)
        feature_columns.append(name)

    for window in cfg.volatility_windows:
        name = f"vol_{window}"
        data[name] = (
            returns.groupby(data["symbol"], sort=False)
            .rolling(window, min_periods=window)
            .std()
            .reset_index(level=0, drop=True)
        )
        feature_columns.append(name)

    for window in cfg.trend_windows:
        average = close.transform(lambda values, w=window: values.rolling(w).mean())
        name = f"ma_gap_{window}"
        data[name] = data["close"] / average - 1
        feature_columns.append(name)

    rolling_high = close.transform(lambda values: values.rolling(cfg.drawdown_window).max())
    data["drawdown_60"] = data["close"] / rolling_high - 1
    feature_columns.append("drawdown_60")

    intraday_range = (data["high"] - data["low"]) / data["close"].replace(0, np.nan)
    data["range"] = intraday_range.replace([np.inf, -np.inf], np.nan)
    feature_columns.append("range")

    volume_average = grouped["volume"].transform(
        lambda values: values.rolling(cfg.volume_window).mean()
    )
    data["volume_ratio"] = data["volume"] / volume_average.replace(0, np.nan)
    feature_columns.append("volume_ratio")

    if "amount" in data.columns:
        amount_average = grouped["amount"].transform(
            lambda values: values.rolling(cfg.volume_window).mean()
        )
        data["amount_ratio"] = data["amount"] / amount_average.replace(0, np.nan)
        feature_columns.append("amount_ratio")

    future_close = close.shift(-cfg.prediction_horizon)
    data["future_return"] = future_close / data["close"] - 1
    data["feature_complete"] = data[feature_columns].notna().all(axis=1)
    data.attrs["feature_columns"] = feature_columns
    return data


def _make_model(model_type: str, random_state: int):
    if model_type == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(
            n_estimators=120,
            max_depth=5,
            min_samples_leaf=30,
            n_jobs=-1,
            random_state=random_state,
        )
    if model_type == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(
            max_iter=160,
            learning_rate=0.04,
            max_leaf_nodes=15,
            l2_regularization=0.05,
            random_state=random_state,
        )
    if model_type == "ridge":
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge

        return make_pipeline(StandardScaler(), Ridge(alpha=10.0, random_state=random_state))
    raise ValueError("model_type must be random_forest, hist_gradient_boosting or ridge")


def rolling_ml_prediction_weights(
    bars: pd.DataFrame,
    *,
    model_type: str = "random_forest",
    prediction_horizon: int = 5,
    train_window_days: int = 756,
    retrain: str = "monthly",
    rebalance: str = "daily",
    top_n: int = 3,
    minimum_prediction: float = 0.0,
    target_volatility: float | None = 0.20,
    max_gross: float = 1.0,
    min_train_observations: int = 800,
    random_state: int = 42,
    include_predictions: bool = False,
) -> pd.DataFrame:
    """Train a rolling CPU ML model and convert predictions into target weights."""

    if top_n < 1:
        raise ValueError("top_n must be positive")
    if train_window_days <= prediction_horizon:
        raise ValueError("train_window_days must exceed prediction_horizon")
    features = ml_feature_frame(
        bars, MLFeatureConfig(prediction_horizon=prediction_horizon)
    )
    feature_columns = list(features.attrs["feature_columns"])
    dates = pd.Index(sorted(features["timestamp"].unique()))
    prediction_rows = _rebalance_filter(features, rebalance)
    prediction_dates = pd.Index(sorted(prediction_rows["timestamp"].unique()))
    if retrain == "daily":
        retrain_dates = set(prediction_dates)
    elif retrain == "weekly":
        retrain_dates = set(_rebalance_filter(features, "weekly")["timestamp"].unique())
    elif retrain == "monthly":
        retrain_dates = set(_rebalance_filter(features, "monthly")["timestamp"].unique())
    else:
        raise ValueError("retrain must be daily, weekly or monthly")

    model = None
    predictions: list[pd.DataFrame] = []
    for timestamp in prediction_dates:
        date_index = dates.get_loc(timestamp)
        known_label_index = date_index - prediction_horizon
        if known_label_index < 0:
            continue
        train_end = dates[known_label_index]
        train_start = dates[max(0, known_label_index - train_window_days + 1)]
        should_retrain = model is None or timestamp in retrain_dates
        if should_retrain:
            train = features[
                (features["timestamp"] >= train_start)
                & (features["timestamp"] <= train_end)
                & features["feature_complete"]
                & features["future_return"].notna()
            ]
            if len(train) < min_train_observations:
                continue
            model = _make_model(model_type, random_state)
            model.fit(train[feature_columns], train["future_return"])
        if model is None:
            continue
        current = prediction_rows[
            (prediction_rows["timestamp"] == timestamp)
            & prediction_rows["feature_complete"]
        ].copy()
        if current.empty:
            continue
        current["prediction"] = model.predict(current[feature_columns])
        predictions.append(current)

    if not predictions:
        return pd.DataFrame(columns=["timestamp", "symbol", "weight"])

    scored = pd.concat(predictions, ignore_index=True)
    eligible = scored["prediction"] > minimum_prediction
    rank = scored["prediction"].where(eligible).groupby(scored["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)
    # Reuse the existing inverse-volatility risk scaling. The vol_20 feature is
    # daily volatility, while _risk_weights expects annualized volatility.
    scored["volatility"] = scored["vol_20"] * np.sqrt(252)
    scored["weight"] = _risk_weights(
        scored,
        scored["prediction"].where(selected, 0.0),
        target_volatility=target_volatility,
        max_gross=max_gross,
    )
    columns = ["timestamp", "symbol", "weight"]
    if include_predictions:
        columns.append("prediction")
    return scored[columns]
