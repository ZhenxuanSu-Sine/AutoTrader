"""Deterministic tests; no downloaded or invented data is reported as market history."""
import unittest
import numpy as np
import pandas as pd
from scripts.backtest_gold_daily import backtest, normalize_sge

class GoldDailyBacktestTests(unittest.TestCase):
    def make_bars(self):
        dates=pd.bdate_range("2024-01-01",periods=220)
        close=np.r_[np.linspace(450,510,110),np.linspace(510,440,110)]
        return pd.DataFrame({"date":dates,"open":close,"high":close+1,
                             "low":close-1,"close":close})
    def test_no_lookahead(self):
        df=self.make_bars()
        curve,trades,metrics=backtest(df)
        self.assertEqual(len(curve),len(df))
        self.assertEqual(metrics["bars"],220)
        if len(trades):
            first=trades.iloc[0]
            day=df.index[df.date==pd.Timestamp(first["date"])][0]
            self.assertGreaterEqual(day,60)
    def test_nonzero_spread_reduces_equity(self):
        df=self.make_bars()
        _,_,a=backtest(df,spread_per_gram=0)
        _,_,b=backtest(df,spread_per_gram=3.8)
        self.assertLessEqual(b["final_cny"],a["final_cny"])
    def test_invalid_data_rejected(self):
        with self.assertRaises(ValueError):
            normalize_sge(pd.DataFrame({"date":["2024-01-01"],"close":[500]}))
    def test_minute_execution_not_claimed(self):
        _,_,m=backtest(self.make_bars())
        self.assertIn("NOT bank minute quotes",m["data_type"])

if __name__=="__main__": unittest.main()
