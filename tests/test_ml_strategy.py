import unittest

import numpy as np
import pandas as pd

from autotrader.strategies.ml import ml_feature_frame, rolling_ml_prediction_weights


def panel(days=180):
    dates = pd.date_range("2023-01-02", periods=days, freq="B")
    rows = []
    for number, symbol in enumerate(["A", "B", "C", "D"]):
        close = 20 + np.arange(days) * (0.04 - number * 0.01)
        for timestamp, price in zip(dates, close):
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": price,
                    "high": price + 0.2,
                    "low": price - 0.2,
                    "close": price,
                    "volume": 100_000 + number,
                }
            )
    return pd.DataFrame(rows)


class MLStrategyTests(unittest.TestCase):
    def test_feature_frame_uses_grouped_future_returns(self):
        data = panel()
        features = ml_feature_frame(data)
        symbol = features[features["symbol"] == "A"].reset_index(drop=True)
        expected = symbol.loc[5, "close"] / symbol.loc[0, "close"] - 1
        self.assertAlmostEqual(symbol.loc[0, "future_return"], expected)
        self.assertIn("ret_20", features.attrs["feature_columns"])

    def test_rolling_ml_weights_are_long_only_and_causal(self):
        original = panel(days=220)
        altered = original.copy()
        cutoff = altered["timestamp"].sort_values().unique()[-20]
        altered.loc[altered["timestamp"] >= cutoff, ["open", "high", "low", "close"]] *= 2
        kwargs = dict(
            model_type="ridge",
            prediction_horizon=5,
            train_window_days=80,
            retrain="monthly",
            rebalance="weekly",
            top_n=2,
            max_gross=1.0,
            min_train_observations=100,
        )
        first = rolling_ml_prediction_weights(original, **kwargs)
        second = rolling_ml_prediction_weights(altered, **kwargs)
        self.assertGreater(len(first), 0)
        self.assertTrue((first["weight"] >= 0).all())
        self.assertTrue((first.groupby("timestamp")["weight"].sum() <= 1 + 1e-9).all())
        before = first[first["timestamp"] < cutoff].reset_index(drop=True)
        other_before = second[second["timestamp"] < cutoff].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, other_before)

    def test_rolling_ml_can_include_predictions(self):
        weights = rolling_ml_prediction_weights(
            panel(days=220),
            model_type="ridge",
            prediction_horizon=5,
            train_window_days=80,
            retrain="monthly",
            rebalance="weekly",
            top_n=2,
            max_gross=1.0,
            min_train_observations=100,
            include_predictions=True,
        )
        self.assertIn("prediction", weights.columns)


if __name__ == "__main__":
    unittest.main()
