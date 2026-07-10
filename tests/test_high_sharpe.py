import unittest

import numpy as np
import pandas as pd

from autotrader.strategies.high_sharpe import (
    blend_weights,
    breakout_stock_selection_weights,
    breadth_regime_weights,
    contraction_breakout_weights,
    defensive_composite_weights,
    dual_momentum_rotation_weights,
    multifactor_stock_selection_weights,
    multi_horizon_trend_weights,
    sparse_breakout_trend_weights,
    weighted_blend_weights,
)


def panel(days=180):
    dates = pd.date_range("2023-01-02", periods=days, freq="B")
    rows = []
    for number, symbol in enumerate(["A", "B", "C"]):
        close = 20 + np.arange(days) * (0.03 - number * 0.01)
        for timestamp, price in zip(dates, close):
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "open": price,
                    "high": price + 0.2,
                    "low": price - 0.2,
                    "close": price,
                    "volume": 100_000,
                }
            )
    return pd.DataFrame(rows)


class HighSharpeStrategyTests(unittest.TestCase):
    def assert_valid_weights(self, weights):
        self.assertGreater(len(weights), 0)
        self.assertTrue((weights["weight"] >= 0).all())
        gross = weights.groupby("timestamp")["weight"].sum()
        self.assertTrue((gross <= 1 + 1e-9).all())

    def test_candidate_weights_are_long_only_and_unlevered(self):
        data = panel()
        candidates = [
            multi_horizon_trend_weights(data, horizons=(20, 60), vol_window=20),
            dual_momentum_rotation_weights(data, lookback=60, top_n=2),
            defensive_composite_weights(data, momentum_windows=(20, 60), top_n=2),
            breadth_regime_weights(data, trend_window=60),
            multifactor_stock_selection_weights(
                data,
                top_n=2,
                momentum_windows=(20, 60),
                vol_window=20,
                minimum_history=60,
                trend_window=40,
            ),
        ]
        for weights in candidates:
            self.assert_valid_weights(weights)

    def test_blend_averages_exposure(self):
        first = pd.DataFrame(
            {"timestamp": [pd.Timestamp("2024-01-01")], "symbol": ["A"], "weight": [1.0]}
        )
        second = first.assign(weight=0.0)
        blended = blend_weights(first, second)
        self.assertEqual(blended.iloc[0]["weight"], 0.5)

    def test_stock_selection_is_top_n_and_causal(self):
        original = panel()
        altered = original.copy()
        cutoff = altered["timestamp"].sort_values().unique()[-20]
        altered.loc[altered["timestamp"] >= cutoff, ["open", "high", "low", "close"]] *= 3
        kwargs = dict(
            top_n=2,
            momentum_windows=(20, 60),
            vol_window=20,
            minimum_history=60,
            trend_window=40,
        )
        first = multifactor_stock_selection_weights(original, **kwargs)
        second = multifactor_stock_selection_weights(altered, **kwargs)
        selected_count = first[first["weight"] > 0].groupby("timestamp")["symbol"].count()
        self.assertTrue((selected_count <= 2).all())
        before = first[first["timestamp"] < cutoff].reset_index(drop=True)
        other_before = second[second["timestamp"] < cutoff].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, other_before)

    def test_aggressive_breakout_respects_leverage_cap(self):
        weights = breakout_stock_selection_weights(
            panel(),
            top_n=2,
            breakout_window=40,
            trend_window=40,
            minimum_history=60,
            max_gross=2.0,
        )
        gross = weights.groupby("timestamp")["weight"].sum()
        self.assertTrue((gross <= 2 + 1e-9).all())

    def test_sparse_short_term_candidates_respect_leverage_cap(self):
        data = panel(days=220)
        candidates = [
            sparse_breakout_trend_weights(
                data,
                top_n=2,
                breakout_window=40,
                minimum_history=60,
                trend_window=40,
                volume_multiple=1.0,
                max_gross=2.0,
            ),
            contraction_breakout_weights(
                data,
                top_n=2,
                breakout_window=40,
                minimum_history=60,
                trend_window=40,
                max_gross=2.0,
            ),
        ]
        for weights in candidates:
            self.assertGreater(len(weights), 0)
            self.assertTrue((weights["weight"] >= 0).all())
            gross = weights.groupby("timestamp")["weight"].sum()
            self.assertTrue((gross <= 2 + 1e-9).all())

    def test_weighted_blend_preserves_allocations(self):
        frame = pd.DataFrame(
            {"timestamp": [pd.Timestamp("2024-01-01")], "symbol": ["A"], "weight": [1.0]}
        )
        blended = weighted_blend_weights([frame, frame], [0.7, 0.3])
        self.assertAlmostEqual(blended.iloc[0]["weight"], 1.0)


if __name__ == "__main__":
    unittest.main()
