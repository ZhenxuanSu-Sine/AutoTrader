import unittest

import pandas as pd

from autotrader.strategies.defensive import large_cap_low_vol_monthly_weights


class DefensiveStrategyTests(unittest.TestCase):
    def test_large_cap_low_vol_weights_select_top_n_and_sum_to_one(self):
        rows = []
        for i, symbol in enumerate(["A", "B", "C"]):
            rows.append(
                {
                    "timestamp": pd.Timestamp("2024-01-02"),
                    "symbol": symbol,
                    "history": 300,
                    "liquidity_20_rank": 0.9,
                    "float_market_cap": 100 + i,
                    "float_market_cap_rank": 0.7 + i * 0.1,
                    "vol_60": 0.1 + i * 0.1,
                    "vol_60_rank": 1.0 - i * 0.2,
                    "drawdown_120_rank": 0.8,
                }
            )
        weights = large_cap_low_vol_monthly_weights(
            pd.DataFrame(rows), top_n=2, allocation="cap"
        )
        self.assertEqual(len(weights), 2)
        self.assertAlmostEqual(weights["weight"].sum(), 1.0)
        self.assertTrue((weights["weight"] > 0).all())

    def test_requires_expected_columns(self):
        with self.assertRaises(ValueError):
            large_cap_low_vol_monthly_weights(pd.DataFrame())


if __name__ == "__main__":
    unittest.main()
