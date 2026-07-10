import unittest

import pandas as pd

from autotrader.backtest import BacktestConfig
from autotrader.core import CostModel
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies import buy_and_hold_weights


def sample_bars():
    dates = pd.date_range("2024-01-01", "2024-08-30", freq="B")
    close = pd.Series(range(len(dates)), dtype=float) * 0.02 + 10
    return pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": "600000",
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 100_000,
        }
    )


class RollingTests(unittest.TestCase):
    def evaluator(self):
        return RollingWindowBacktester(
            BacktestConfig(
                initial_cash=10_000,
                cost=CostModel(
                    commission_rate=0,
                    minimum_commission=0,
                    stamp_duty_rate=0,
                    slippage_rate=0,
                ),
            ),
            RollingWindowConfig((1, 3)),
        )

    @staticmethod
    def factory(context, start, end):
        if context["timestamp"].max() > end:
            raise AssertionError("factory received data beyond its window end")
        current = context[context["timestamp"].between(start, end, inclusive="both")]
        return buy_and_hold_weights(current)

    def test_windows_are_independent_and_liquidated(self):
        result = self.evaluator().run(sample_bars(), {"buy_hold": self.factory})
        self.assertEqual(set(result.windows["window_months"]), {1, 3})
        self.assertTrue((result.windows["trade_count"] == 2).all())
        self.assertTrue((result.windows["closed_trade_count"] == 1).all())

    def test_summary_contains_requested_return_distribution(self):
        result = self.evaluator().run(sample_bars(), {"buy_hold": self.factory})
        expected = {
            "profitable_window_ratio",
            "window_return_mean",
            "window_return_median",
            "window_return_std",
            "window_return_q05",
            "window_return_q25",
            "window_return_q75",
            "window_return_q95",
        }
        self.assertTrue(expected.issubset(result.summary.columns))

    def test_future_rows_do_not_change_finished_window(self):
        original = sample_bars()
        altered = original.copy()
        altered.loc[altered["timestamp"] >= "2024-05-01", ["open", "high", "low", "close"]] *= 10
        first = self.evaluator().run(original, {"buy_hold": self.factory}).windows
        second = self.evaluator().run(altered, {"buy_hold": self.factory}).windows
        key = (first["window_months"] == 3) & (first["window_start"] == pd.Timestamp("2024-01-01"))
        other_key = (second["window_months"] == 3) & (second["window_start"] == pd.Timestamp("2024-01-01"))
        self.assertAlmostEqual(
            first.loc[key, "window_return"].iloc[0],
            second.loc[other_key, "window_return"].iloc[0],
        )


if __name__ == "__main__":
    unittest.main()

