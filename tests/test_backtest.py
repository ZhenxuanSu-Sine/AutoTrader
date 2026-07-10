import unittest

import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.core import CostModel


def bars(prices, timestamps=None):
    if timestamps is None:
        timestamps = pd.date_range("2024-01-02", periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": "600000",
            "open": prices,
            "high": [price + 1 for price in prices],
            "low": [price - 1 for price in prices],
            "close": prices,
            "volume": 100_000,
        }
    )


class BacktestTests(unittest.TestCase):
    def engine(self, **kwargs):
        config = BacktestConfig(
            initial_cash=10_000,
            lot_size=100,
            cost=CostModel(commission_rate=0, minimum_commission=0, stamp_duty_rate=0, slippage_rate=0),
            **kwargs,
        )
        return PortfolioEngine(config)

    def test_signal_executes_on_next_bar(self):
        data = bars([10, 20, 30])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [1.0]}
        )
        result = self.engine().run(data, weights)
        self.assertEqual(result.trades.iloc[0]["timestamp"], data.iloc[1]["timestamp"])
        self.assertEqual(result.trades.iloc[0]["price"], 20)
        self.assertEqual(result.metrics["final_equity"], 15_000)

    def test_buy_quantity_is_rounded_to_board_lot(self):
        data = bars([16, 16, 16])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [0.5]}
        )
        result = self.engine().run(data, weights)
        self.assertEqual(result.trades.iloc[0]["quantity"], 300)

    def test_t_plus_one_blocks_same_day_sale(self):
        times = pd.to_datetime(["2024-01-02 09:31", "2024-01-02 09:32", "2024-01-02 09:33"])
        data = bars([10, 10, 10], times)
        weights = pd.DataFrame(
            {
                "timestamp": times[:2],
                "symbol": ["600000", "600000"],
                "weight": [1.0, 0.0],
            }
        )
        result = self.engine(t_plus_one=True).run(data, weights)
        self.assertEqual(result.trades["side"].tolist(), ["buy"])

    def test_rejects_overallocated_weights(self):
        data = bars([10, 10])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [1.1]}
        )
        with self.assertRaisesRegex(ValueError, "exceed"):
            self.engine().run(data, weights)

    def test_missing_bar_uses_last_close_for_valuation(self):
        data = bars([10, 10, 10])
        extra = data.iloc[[2]].copy()
        extra["symbol"] = "000001"
        data = pd.concat([data.iloc[:2], extra], ignore_index=True)
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [1.0]}
        )
        result = self.engine().run(data, weights)
        self.assertEqual(result.equity.iloc[-1]["equity"], 10_000)

    def test_rejects_unknown_weight_symbol(self):
        data = bars([10, 10])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["000001"], "weight": [1.0]}
        )
        with self.assertRaisesRegex(ValueError, "absent"):
            self.engine().run(data, weights)

    def test_terminal_liquidation_closes_position(self):
        data = bars([10, 10, 11])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [1.0]}
        )
        result = self.engine(liquidate_at_end=True).run(data, weights)
        self.assertEqual(result.trades["side"].tolist(), ["buy", "sell"])
        self.assertEqual(result.trades.iloc[-1]["reason"], "terminal_liquidation")
        self.assertEqual(result.positions.iloc[-1]["timestamp"], data.iloc[1]["timestamp"])
        self.assertEqual(result.metrics["final_equity"], 11_000)
        self.assertEqual(result.metrics["closed_trade_count"], 1)

    def test_explicit_leverage_can_exceed_cash(self):
        data = bars([10, 10, 11])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [2.0]}
        )
        result = self.engine(max_gross_exposure=2.0, liquidate_at_end=True).run(data, weights)
        self.assertEqual(result.trades.iloc[0]["quantity"], 2_000)
        self.assertEqual(result.metrics["final_equity"], 12_000)

    def test_negative_cash_accrues_financing_cost(self):
        data = bars([10, 10, 10])
        weights = pd.DataFrame(
            {"timestamp": [data.iloc[0]["timestamp"]], "symbol": ["600000"], "weight": [2.0]}
        )
        result = self.engine(
            max_gross_exposure=2.0,
            annual_borrow_rate=0.252,
            liquidate_at_end=True,
        ).run(data, weights)
        self.assertAlmostEqual(result.metrics["financing_cost"], 10.0)
        self.assertAlmostEqual(result.metrics["final_equity"], 9_990.0)



if __name__ == "__main__":
    unittest.main()
