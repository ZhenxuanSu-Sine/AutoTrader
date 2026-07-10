import unittest

import pandas as pd

from autotrader.strategies.overlays import cap_gross_exposure, scale_weights


class OverlayTests(unittest.TestCase):
    def test_scale_weights_applies_multiplier(self):
        weights = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-01-01")],
                "symbol": ["A"],
                "weight": [0.5],
            }
        )
        scaled = scale_weights(weights, 0.4)
        self.assertAlmostEqual(scaled.iloc[0]["weight"], 0.2)

    def test_cap_gross_exposure_scales_timestamp_proportionally(self):
        weights = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")],
                "symbol": ["A", "B"],
                "weight": [0.8, 0.7],
            }
        )
        capped = cap_gross_exposure(weights, 1.0)
        self.assertAlmostEqual(capped["weight"].sum(), 1.0)
        self.assertAlmostEqual(
            capped.loc[capped["symbol"] == "A", "weight"].iloc[0]
            / capped.loc[capped["symbol"] == "B", "weight"].iloc[0],
            0.8 / 0.7,
        )


if __name__ == "__main__":
    unittest.main()
