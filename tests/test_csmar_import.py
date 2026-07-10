import tempfile
import unittest
from pathlib import Path

import pandas as pd

from autotrader.data.sources.csmar import (
    format_symbol,
    normalize_daily_chunk,
    read_company_file,
)


class CSMARImportTests(unittest.TestCase):
    def test_symbol_suffix_uses_market_type(self):
        self.assertEqual(format_symbol("600000", 1), "600000.SH")
        self.assertEqual(format_symbol("000001", 4), "000001.SZ")
        self.assertEqual(format_symbol("688001", 32), "688001.SH")
        self.assertEqual(format_symbol("920001", 64), "920001.BJ")

    def test_normalize_daily_chunk_filters_non_a_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            company_path = Path(tmp) / "TRD_Co.json"
            company_path.write_text(
                '{"Stkcd":"000001","Stknme":"A","Listdt":"1991-01-01","Statco":"A",'
                '"Statdt":"2024-01-01","Markettype":4,"Curtrd":"CNY"}\n'
                '{"Stkcd":"200001","Stknme":"B","Listdt":"1991-01-01","Statco":"A",'
                '"Statdt":"2024-01-01","Markettype":8,"Curtrd":"HKD"}\n',
                encoding="utf-8",
            )
            company = read_company_file(company_path)
            chunk = pd.DataFrame(
                [
                    {
                        "Stkcd": "000001",
                        "Trddt": "2024-01-02",
                        "Opnprc": 10,
                        "Hiprc": 11,
                        "Loprc": 9,
                        "Clsprc": 10.5,
                        "Dnshrtrd": 1000,
                        "Dnvaltrd": 10_500,
                        "Dsmvosd": 1,
                        "Dsmvtll": 2,
                        "Dretwd": 0.01,
                        "Dretnd": 0.01,
                        "ChangeRatio": 0.01,
                    },
                    {
                        "Stkcd": "200001",
                        "Trddt": "2024-01-02",
                        "Opnprc": 10,
                        "Hiprc": 11,
                        "Loprc": 9,
                        "Clsprc": 10.5,
                        "Dnshrtrd": 1000,
                        "Dnvaltrd": 10_500,
                        "Dsmvosd": 1,
                        "Dsmvtll": 2,
                        "Dretwd": 0.01,
                        "Dretnd": 0.01,
                        "ChangeRatio": 0.01,
                    },
                ]
            )
            bars = normalize_daily_chunk(chunk, company)
            self.assertEqual(bars["symbol"].tolist(), ["000001.SZ"])
            self.assertIn("return_with_dividend", bars.columns)


if __name__ == "__main__":
    unittest.main()
