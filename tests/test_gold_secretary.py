"""Synthetic fixtures verify mechanics; not market performance."""
import unittest
import numpy as np
import pandas as pd
from scripts.backtest_gold_secretary import secretary_backtest


class SecretaryTests(unittest.TestCase):
    def bars(self, prices):
        dates=pd.bdate_range("2024-01-01",periods=len(prices))
        p=np.asarray(prices,dtype=float)
        return pd.DataFrame({"date":dates,"open":p,"close":p,
                             "high":p+1,"low":p-1})

    def test_forced_buy_and_sell_in_flat_market(self):
        _,trades,_=secretary_backtest(self.bars([500]*70),
                                     buy_window=30,sell_window=30)
        self.assertEqual(trades.iloc[0].action,"BUY")
        self.assertEqual(trades.iloc[0].reason,"window_expiry")
        self.assertEqual(trades.iloc[1].action,"SELL")
        self.assertEqual(trades.iloc[1].reason,"window_expiry")
        self.assertEqual(trades.iloc[0].date,"2024-02-09") # session 30
        self.assertEqual(trades.iloc[1].date,"2024-03-22") # session 60

    def test_record_buy_after_observation(self):
        prices=[500]*11+[499]+[500]*55
        _,trades,_=secretary_backtest(self.bars(prices))
        self.assertEqual(trades.iloc[0].action,"BUY")
        self.assertEqual(trades.iloc[0].reason,"record")
        self.assertEqual(trades.iloc[0].date,"2024-01-16")

    def test_future_prices_do_not_change_past_actions(self):
        a=self.bars([500]*90)
        b=a.copy()
        b.loc[60:,"open"]=1000
        b.loc[60:,"close"]=1000
        _,ta,_=secretary_backtest(a)
        _,tb,_=secretary_backtest(b)
        self.assertEqual(ta.iloc[:2].to_dict("records"),tb.iloc[:2].to_dict("records"))

    def test_cost_reduces_flat_market_equity(self):
        a=self.bars([500]*70)
        _,_,free=secretary_backtest(a,spread_per_gram=0)
        _,_,paid=secretary_backtest(a,spread_per_gram=3.8)
        self.assertLess(paid["final_cny"],free["final_cny"])

    def test_invalid_parameters(self):
        a=self.bars([500]*70)
        for kw in ({"buy_window":1},{"sell_fraction":1},
                   {"buy_fraction":0},{"stop_loss":-0.1}):
            with self.assertRaises(ValueError):
                secretary_backtest(a,**kw)


if __name__=="__main__":
    unittest.main()
