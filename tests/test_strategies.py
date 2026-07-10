import unittest

import pandas as pd

from autotrader.strategies import (
    cross_sectional_momentum_weights,
    equal_weight_weights,
    time_series_momentum_weights,
)


def panel(days=70):
    dates = pd.date_range("2024-01-02", periods=days, freq="B")
    rows = []
    for symbol, step in (("A", 1.0), ("B", -0.02), ("C", 0.1)):
        for index, timestamp in enumerate(dates):
            close = 20 + index * step
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": close,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "volume": 1000,
                }
            )
    return pd.DataFrame(rows)


class StrategyTests(unittest.TestCase):
    def test_equal_weight_sums_to_one(self):
        weights = equal_weight_weights(panel())
        self.assertAlmostEqual(weights["weight"].sum(), 1.0)

    def test_time_series_momentum_is_trailing(self):
        weights = time_series_momentum_weights(panel(), lookback=20)
        latest = weights[weights["timestamp"] == weights["timestamp"].max()]
        mapping = latest.set_index("symbol")["weight"].to_dict()
        self.assertEqual(mapping["A"], 1.0)
        self.assertEqual(mapping["B"], 0.0)

    def test_cross_sectional_momentum_selects_top_asset(self):
        weights = cross_sectional_momentum_weights(panel(), lookback=20, top_n=1)
        latest = weights[weights["timestamp"] == weights["timestamp"].max()]
        winner = latest.loc[latest["weight"] == 1.0, "symbol"].tolist()
        self.assertEqual(winner, ["A"])


if __name__ == "__main__":
    unittest.main()

