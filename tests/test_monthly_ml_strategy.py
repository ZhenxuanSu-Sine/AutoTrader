from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from autotrader.strategies.monthly_ml import MonthlyMLConfig, monthly_ml_prediction_weights


def sample_monthly_features(months: int = 48, symbols: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2020-01-02", periods=months, freq="BMS")
    rows = []
    for month_index, timestamp in enumerate(dates):
        for symbol_index in range(symbols):
            symbol = f"{symbol_index:06d}.SZ"
            close = 10 + month_index * 0.05 + symbol_index * 0.01
            ret_signal = (symbol_index % 20) / 20
            low_vol_signal = 1 - (symbol_index % 10) / 10
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "close": close,
                    "history": 300 + month_index,
                    "ret_5_rank": ret_signal,
                    "ret_20_rank": ret_signal,
                    "ret_60_rank": ret_signal,
                    "ret_120_rank": ret_signal,
                    "vol_20_rank": low_vol_signal,
                    "vol_60_rank": low_vol_signal,
                    "drawdown_120_rank": low_vol_signal,
                    "liquidity_20_rank": 0.8,
                    "float_market_cap": 1_000_000 + symbol_index,
                    "float_market_cap_rank": symbol_index / symbols,
                    "total_market_cap_rank": symbol_index / symbols,
                    "vol_60": 0.2 + symbol_index / 10_000,
                }
            )
    return pd.DataFrame(rows)


class MonthlyMLStrategyTests(unittest.TestCase):
    def test_monthly_ml_weights_are_long_only_and_sum_to_one(self) -> None:
        features = sample_monthly_features()
        weights = monthly_ml_prediction_weights(
            features,
            MonthlyMLConfig(
                train_window_months=24,
                min_train_months=12,
                min_train_observations=500,
                top_n=5,
                allocation="equal",
            ),
        )
        self.assertFalse(weights.empty)
        self.assertTrue((weights["weight"] >= 0).all())
        sums = weights.groupby("timestamp")["weight"].sum()
        np.testing.assert_allclose(sums.to_numpy(), np.ones(len(sums)))
        self.assertLessEqual(weights.groupby("timestamp")["symbol"].nunique().max(), 5)

    def test_future_rows_do_not_change_past_predictions(self) -> None:
        features = sample_monthly_features(months=48)
        config = MonthlyMLConfig(
            train_window_months=24,
            min_train_months=12,
            min_train_observations=500,
            top_n=5,
            allocation="equal",
        )
        original = monthly_ml_prediction_weights(features, config)
        cutoff = original["timestamp"].sort_values().unique()[5]
        changed = features.copy()
        changed.loc[changed["timestamp"] > cutoff, "ret_120_rank"] = 1 - changed.loc[
            changed["timestamp"] > cutoff, "ret_120_rank"
        ]
        rerun = monthly_ml_prediction_weights(changed, config)
        left = original[original["timestamp"] <= cutoff].reset_index(drop=True)
        right = rerun[rerun["timestamp"] <= cutoff].reset_index(drop=True)
        pd.testing.assert_frame_equal(left, right)


if __name__ == "__main__":
    unittest.main()
