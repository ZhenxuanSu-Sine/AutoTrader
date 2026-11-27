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
        self.assertEqual(trades.iloc[0].date,"2024-02-09") # last open inside 30-session buy window
        self.assertEqual(trades.iloc[1].date,"2024-03-22") # last open inside 30-session sell window

    def test_record_buy_after_observation(self):
        prices=[500]*12+[499]+[500]*55
        _,trades,_=secretary_backtest(self.bars(prices))
        self.assertEqual(trades.iloc[0].action,"BUY")
        self.assertEqual(trades.iloc[0].reason,"record")
        self.assertEqual(trades.iloc[0].date,"2024-01-18")

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


    def test_four_expiry_modes_flat_market(self):
        for fb, fs in ((True, True), (False, True), (True, False), (False, False)):
            with self.subTest(force_buy=fb, force_sell=fs):
                curve, trades, m = secretary_backtest(
                    self.bars([500]*70), force_buy=fb, force_sell=fs)
                self.assertEqual(curve.grams.iloc[-1], 0)
                if not fb:
                    self.assertEqual(len(trades), 0)
                    self.assertEqual(m["skipped_buy"], 2)
                    self.assertEqual(m["skipped_sell"], 0)
                    self.assertEqual(m["total_return"], 0)
                else:
                    self.assertEqual(list(trades.action), ["BUY", "SELL"])
                    self.assertEqual(trades.iloc[1].reason,
                                     "window_expiry" if fs else "evaluation_end")
                    self.assertEqual(m["skipped_sell"], 0 if fs else 1)

    def test_stop_loss_overrides_expiry_and_holding_limit(self):
        a = self.bars([500]*70)
        a.loc[29, "close"] = 450
        _, trades, _ = secretary_backtest(
            a, stop_loss=.05, max_holding_days=1)
        self.assertEqual(trades.iloc[1].reason, "stop_loss")
        self.assertEqual(trades.iloc[1].date, str(a.date.iloc[30].date()))
        self.assertAlmostEqual(trades.iloc[1].price, 498.1)

    def test_holding_limit_when_sell_can_be_abandoned(self):
        a = self.bars([500]*70)
        _, trades, _ = secretary_backtest(
            a, force_sell=False, max_holding_days=5)
        self.assertEqual(trades.iloc[1].reason, "max_holding_days")
        self.assertEqual(trades.iloc[1].date, str(a.date.iloc[34].date()))

    def test_terminal_open_cannot_open_position(self):
        curve, trades, m = secretary_backtest(self.bars([500]*30))
        self.assertEqual(len(trades), 0)
        self.assertEqual(curve.grams.iloc[-1], 0)
        self.assertEqual(m["terminal_liquidations"], 0)

    def test_terminal_exit_uses_open_not_close(self):
        a = self.bars([500]*40)
        b = a.copy()
        b.loc[39, "close"] = 900
        _, ta, ma = secretary_backtest(a)
        _, tb, mb = secretary_backtest(b)
        self.assertEqual(ta.to_dict("records"), tb.to_dict("records"))
        self.assertEqual(ma["final_cny"], mb["final_cny"])
        self.assertEqual(ma["terminal_liquidations"], 1)


if __name__=="__main__":
    unittest.main()
