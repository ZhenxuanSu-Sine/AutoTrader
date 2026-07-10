import unittest

import pandas as pd

from autotrader.factors import evaluate_factor, forward_returns, momentum


def panel():
    rows = []
    dates = pd.date_range("2024-01-02", periods=5, freq="D")
    for symbol, closes in (("A", [10, 11, 12, 13, 14]), ("B", [10, 9, 8, 7, 6])):
        for timestamp, close in zip(dates, closes):
            rows.append(
                {
                    "timestamp": timestamp, "symbol": symbol, "open": close,
                    "high": close + 1, "low": close - 1, "close": close, "volume": 100,
                }
            )
    return pd.DataFrame(rows)


class FactorTests(unittest.TestCase):
    def test_forward_return_does_not_cross_symbols(self):
        returns = forward_returns(panel(), periods=1)
        last_a = returns[returns["symbol"] == "A"].iloc[-1]
        self.assertTrue(pd.isna(last_a["forward_return"]))

    def test_momentum_uses_trailing_prices(self):
        factor = momentum(panel(), window=2)
        value = factor[(factor["symbol"] == "A") & (factor["timestamp"] == pd.Timestamp("2024-01-04"))]
        self.assertAlmostEqual(value.iloc[0]["factor"], 0.2)

    def test_factor_report_detects_positive_rank_ic(self):
        data = panel()
        factor = data[["timestamp", "symbol"]].copy()
        factor["factor"] = factor["symbol"].map({"A": 1.0, "B": -1.0})
        report = evaluate_factor(factor, data, periods=1, quantiles=2)
        self.assertGreater(report.summary["mean_rank_ic"], 0.9)
        self.assertGreater(report.summary["top_bottom_spread"], 0)


if __name__ == "__main__":
    unittest.main()
