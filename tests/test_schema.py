import unittest

import pandas as pd

from autotrader.data import normalize_bars


class SchemaTests(unittest.TestCase):
    def test_normalizes_chinese_provider_columns(self):
        source = pd.DataFrame(
            {
                "日期": ["2024-01-03", "2024-01-02"],
                "开盘": [10.2, 10.0],
                "最高": [10.5, 10.3],
                "最低": [10.0, 9.9],
                "收盘": [10.4, 10.2],
                "成交量": [200, 100],
            }
        )
        bars = normalize_bars(source, symbol="600000")
        self.assertEqual(bars.iloc[0]["timestamp"], pd.Timestamp("2024-01-02"))
        self.assertEqual(bars["symbol"].tolist(), ["600000", "600000"])

    def test_rejects_duplicate_bars(self):
        source = pd.DataFrame(
            {
                "timestamp": ["2024-01-02", "2024-01-02"],
                "symbol": ["600000", "600000"],
                "open": [10, 10], "high": [11, 11], "low": [9, 9],
                "close": [10, 10], "volume": [100, 100],
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize_bars(source)

    def test_rejects_invalid_ohlc(self):
        source = pd.DataFrame(
            {
                "timestamp": ["2024-01-02"], "symbol": ["600000"],
                "open": [10], "high": [9], "low": [8], "close": [10], "volume": [100],
            }
        )
        with self.assertRaisesRegex(ValueError, "high"):
            normalize_bars(source)


if __name__ == "__main__":
    unittest.main()

