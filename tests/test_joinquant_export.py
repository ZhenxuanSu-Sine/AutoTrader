from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from autotrader.exporters.joinquant import csmar_symbol_to_joinquant, export_joinquant_weights


class JoinQuantExportTests(unittest.TestCase):
    def test_symbol_conversion(self) -> None:
        self.assertEqual(csmar_symbol_to_joinquant("600000.SH"), "600000.XSHG")
        self.assertEqual(csmar_symbol_to_joinquant("000001.SZ"), "000001.XSHE")
        self.assertEqual(csmar_symbol_to_joinquant("600519"), "600519.XSHG")
        self.assertEqual(csmar_symbol_to_joinquant("300750"), "300750.XSHE")
        self.assertIsNone(csmar_symbol_to_joinquant("430001.BJ"))

    def test_export_csv_and_python_helper(self) -> None:
        weights = pd.DataFrame(
            {
                "timestamp": ["2024-01-02", "2024-01-02", "2024-02-01"],
                "symbol": ["600000.SH", "000001.SZ", "430001.BJ"],
                "weight": [0.6, 0.4, 1.0],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = export_joinquant_weights(
                weights,
                root / "weights.csv",
                python_path=root / "weights.py",
                summary_path=root / "summary.csv",
                joinquant_weights_path="weights.csv",
                joinquant_max_positions=8,
                joinquant_min_position_value=3000,
                joinquant_cash_buffer=0.05,
            )
            exported = pd.read_csv(result.csv_path)
            self.assertEqual(result.exported_rows, 2)
            self.assertEqual(result.dropped_rows, 1)
            self.assertEqual(exported["code"].tolist(), ["000001.XSHE", "600000.XSHG"])
            self.assertTrue(result.python_path and result.python_path.exists())
            helper = result.python_path.read_text(encoding="utf-8")
            self.assertIn("import jqdata", helper)
            self.assertIn("WEIGHTS_FILE = 'weights.csv'", helper)
            self.assertIn("MAX_POSITIONS = 8", helper)
            self.assertIn("MIN_POSITION_VALUE = 3000.0", helper)
            self.assertIn("CASH_BUFFER = 0.05", helper)
            self.assertIn("LOT_SIZE = 100", helper)
            self.assertIn("read_file(path)", helper)
            self.assertIn("raw.decode('utf-8-sig')", helper)
            self.assertIn("set_benchmark('000300.XSHG')", helper)
            self.assertIn("def market_open(context):", helper)
            self.assertIn("build_target_amounts", helper)
            self.assertIn("round_lot", helper)
            self.assertIn("order_target(security, target_amount)", helper)
            self.assertNotIn("order_target_value", helper)
            self.assertNotIn("order_target_percent", helper)
            self.assertNotIn("WEIGHTS = {", helper)


if __name__ == "__main__":
    unittest.main()
